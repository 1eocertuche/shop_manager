import frappe
from frappe.utils import getdate, nowdate, password
import secrets

# ==============================================================================
# FUNCIÓN 1: SETUP COMPANY ENVIRONMENT (Función interna)
# ==============================================================================
def _setup_company_environment(company_name, abbr):
    # Esta función se mantiene igual, preparando el entorno de la compañía.
    if not frappe.db.exists("Company", company_name):
        company = frappe.new_doc("Company")
        company.update({
            "company_name": company_name,
            "abbr": abbr,
            "country": "Colombia",
            "default_currency": "COP",
            "chart_of_accounts": "Colombia PUC Simple"
        })
        company.insert(ignore_permissions=True)
    
    company_doc = frappe.get_doc("Company", company_name)
    asset_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Asset", "is_group": 1})
    income_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Income", "is_group": 1})
    expense_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Expense", "is_group": 1})
    
    receivable_account_name = f"Deudores - {abbr}"
    if not frappe.db.exists("Account", receivable_account_name):
        frappe.new_doc("Account", account_name="Deudores", parent_account=asset_root, company=company_name, account_type="Receivable").insert(ignore_permissions=True)
    company_doc.default_receivable_account = receivable_account_name
    
    income_account_name = f"Ventas - {abbr}"
    if not frappe.db.exists("Account", income_account_name):
        frappe.new_doc("Account", account_name="Ventas", parent_account=income_root, company=company_name, account_type="Income Account").insert(ignore_permissions=True)
    company_doc.default_income_account = income_account_name
    
    cogs_account_name = f"Costos de los bienes vendidos - {abbr}"
    if not frappe.db.exists("Account", cogs_account_name):
        frappe.new_doc("Account", account_name="Costos de los bienes vendidos", parent_account=expense_root, company=company_name, is_group=1, account_type="Cost of Goods Sold").insert(ignore_permissions=True)
    
    stock_adj_account_name = f"Stock Adjustment - {abbr}"
    if not frappe.db.exists("Account", stock_adj_account_name):
        frappe.new_doc("Account", account_name="Stock Adjustment", parent_account=cogs_account_name, company=company_name, account_type="Stock Adjustment").insert(ignore_permissions=True)
    company_doc.stock_adjustment_account = stock_adj_account_name
    
    stock_asset_account_name = f"Activos de inventario - {abbr}"
    if not frappe.db.exists("Account", stock_asset_account_name):
        frappe.new_doc("Account", account_name="Activos de inventario", parent_account=asset_root, company=company_name, account_type="Stock").insert(ignore_permissions=True)
    company_doc.default_inventory_account = stock_asset_account_name
    
    current_asset_account = f"Activos Corrientes - {abbr}"
    if not frappe.db.exists("Account", current_asset_account):
        current_asset_account = asset_root
    if not frappe.db.exists("Account", {"account_name": "Caja General", "company": company_name}):
        frappe.new_doc("Account", account_name="Caja General", parent_account=current_asset_account, company=company_name, account_type="Cash").insert(ignore_permissions=True)
    
    company_doc.save(ignore_permissions=True)
    
    if not frappe.db.exists("Warehouse", {"warehouse_name": f"Bodega tienda - {abbr}"}):
        frappe.new_doc("Warehouse", warehouse_name=f"Bodega tienda - {abbr}", company=company_name).insert(ignore_permissions=True)
    if not frappe.db.exists("Item Group", "Todos los grupos de productos"):
        frappe.new_doc("Item Group", item_group_name="Todos los grupos de productos", is_group=1).insert(ignore_permissions=True)
    if not frappe.db.exists("Customer Group", "Individual"):
        frappe.new_doc("Customer Group", customer_group_name="Individual").insert(ignore_permissions=True)
    if not frappe.db.exists("Supplier Group", "Todos los grupos de proveedores"):
        frappe.new_doc("Supplier Group", supplier_group_name="Todos los grupos de proveedores").insert(ignore_permissions=True)
    if not frappe.db.exists("UOM", "Unidad"):
        frappe.new_doc("UOM", uom_name="Unidad").insert(ignore_permissions=True)
        
    return f"Environment for company '{company_name}' configured."

# ==============================================================================
# FUNCIÓN 2: CREATE USER AND TRANSACTIONS (Función interna mejorada)
# ==============================================================================
def _create_user_and_transactions(data):
    company_name = data.get("company_name")
    company_doc = frappe.get_doc("Company", company_name)
    seller_email = data.get("user_email")

    # --- Creación de Usuario y Credenciales (si no existe) ---
    if not frappe.db.exists("User", seller_email):
        user = frappe.new_doc("User")
        user.update({
            "email": seller_email,
            "first_name": data.get("user_first_name"),
            "last_name": data.get("user_last_name"),
            "send_welcome_email": 0
        })
        user.add_roles("Accounts User", "Purchase User") # Roles del script original
        user.save(ignore_permissions=True)
        # Generar y guardar claves de API para el nuevo usuario
        api_key, api_secret = user.generate_keys()
        frappe.db.set_value("User", seller_email, "api_key", api_key)
        frappe.db.set_value("User", seller_email, "api_secret", password.encrypt(api_secret))


    # --- Lógica de Transacciones ---
    # Crear Cliente, Proveedor y Artículo (esto puede hacerlo el admin)
    if not frappe.db.exists("Customer", data.get("customer_name")):
        customer = frappe.new_doc("Customer")
        customer.update({"customer_name": data.get("customer_name"), "customer_group": data.get("customer_group")})
        customer.append("accounts", {"company": company_name, "account": company_doc.default_receivable_account})
        customer.insert(ignore_permissions=True)
    
    if not frappe.db.exists("Supplier", data.get("supplier_name")):
        frappe.new_doc("Supplier", supplier_name=data.get("supplier_name"), supplier_group=data.get("supplier_group")).insert(ignore_permissions=True)

    if not frappe.db.exists("Item", data.get("item_code")):
        frappe.new_doc("Item", item_code=data.get("item_code"), item_name=data.get("item_name"), item_group=data.get("item_group"), stock_uom=data.get("uom_name"), is_stock_item=1).insert(ignore_permissions=True)

    # --- PERSONIFICACIÓN DE USUARIO ---
    # Guardamos el usuario original (admin) y cambiamos al usuario vendedor
    original_user = frappe.session.user
    try:
        frappe.set_user(seller_email)

        # Todas las acciones dentro de este bloque 'try' son realizadas POR EL VENDEDOR
        warehouse_name = f"Bodega tienda - {data.get('company_abbr')}"
        
        # 1. Crear Stock Entry (Recibo de Material)
        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.stock_entry_type = "Material Receipt"
        stock_entry.company = company_name
        stock_entry.append("items", {"item_code": data.get("item_code"), "qty": data.get("item_qty", 1) * 10, "t_warehouse": warehouse_name, "basic_rate": data.get("item_rate", 1) * 0.5})
        stock_entry.submit()

        # 2. Crear Sales Invoice
        si = frappe.new_doc("Sales Invoice")
        si.customer = data.get("customer_name")
        si.company = company_name
        si.posting_date = getdate(data.get("posting_date", nowdate()))
        si.update_stock = 1
        si.append("items", {"item_code": data.get("item_code"), "qty": data.get("item_qty"), "rate": data.get("item_rate"), "warehouse": warehouse_name, "income_account": company_doc.default_income_account})
        si.submit()
        
        # 3. Crear Payment Entry
        cash_account = frappe.db.get_value("Account", {"account_name": "Caja General", "company": company_name})
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = data.get("customer_name")
        pe.company = company_name
        pe.paid_amount = si.grand_total
        pe.received_amount = si.grand_total
        pe.paid_to = cash_account
        pe.append("references", {"reference_doctype": "Sales Invoice", "reference_name": si.name, "total_amount": si.grand_total, "outstanding_amount": si.grand_total, "allocated_amount": si.grand_total})
        pe.submit()
    
    finally:
        # Importante: Regresamos al usuario original sin importar si hubo un error o no
        frappe.set_user(original_user)
    
    return {
        "message": f"Transactions created successfully by user {seller_email}.",
        "sales_invoice": si.name,
        "payment_entry": pe.name
    }

# ==============================================================================
# SCRIPT 3: EL ÚNICO ENDPOINT PÚBLICO (ORQUESTADOR)
# ==============================================================================
@frappe.whitelist()
def orchestrate_full_invoice_creation():
    """
    Recibe un JSON y ejecuta el flujo completo de configuración de 
    compañía, creación de usuario y creación de factura de forma atómica.
    """
    data = frappe.local.form_dict
    
    try:
        # ---- PASO 1: Ejecutar la configuración de la compañía ----
        setup_message = _setup_company_environment(data.get("company_name"), data.get("company_abbr"))
        
        # ---- PASO 2: Ejecutar la creación del usuario y las transacciones ----
        invoice_response = _create_user_and_transactions(data)
        
        # ---- PASO 3: Confirmar la transacción y devolver una respuesta combinada ----
        frappe.db.commit()
        
        return {
            "status": "SUCCESS",
            "setup_message": setup_message,
            "invoice_message": invoice_response.get("message"),
            "sales_invoice": invoice_response.get("sales_invoice"),
            "payment_entry": invoice_response.get("payment_entry")
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Full Invoice Orchestration Failed", message=frappe.get_traceback())
        frappe.throw(f"La orquestación falló: {str(e)}")```
