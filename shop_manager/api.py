import frappe
from frappe.utils import getdate, nowdate, password
import secrets # <-- Importante: Módulo para generar secretos

# ==============================================================================
# ENDPOINT 1: SETUP COMPANY AND USER ENVIRONMENT
# ==============================================================================
@frappe.whitelist()
def setup_company_and_user():
    """
    Crea la Compañía, cuentas, grupos por defecto y el Usuario de Ventas.
    Devuelve las credenciales de API para el nuevo usuario.
    """
    data = frappe.local.form_dict
    
    try:
        company_name = data.get("company_name")
        abbr = data.get("company_abbr")
        seller_email = data.get("user_email")

        # --- Setup de la Compañía y Cuentas ---
        # (Esta parte del código no cambia y es correcta)
        if not frappe.db.exists("Company", company_name):
            company = frappe.new_doc("Company")
            company.update({"company_name": company_name, "abbr": abbr, "country": "Colombia", "default_currency": "COP", "chart_of_accounts": "Colombia PUC Simple"})
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
        
        stock_asset_account_name = f"Activos de inventario - {abbr}"
        if not frappe.db.exists("Account", stock_asset_account_name):
            frappe.new_doc("Account", account_name="Activos de inventario", parent_account=asset_root, company=company_name, account_type="Stock").insert(ignore_permissions=True)
        company_doc.default_inventory_account = stock_asset_account_name
        
        cogs_account_name = f"Costos de los bienes vendidos - {abbr}"
        if not frappe.db.exists("Account", cogs_account_name):
            frappe.new_doc("Account", account_name="Costos de los bienes vendidos", parent_account=expense_root, company=company_name, is_group=1, account_type="Cost of Goods Sold").insert(ignore_permissions=True)
        stock_adj_account_name = f"Stock Adjustment - {abbr}"
        if not frappe.db.exists("Account", stock_adj_account_name):
            frappe.new_doc("Account", account_name="Stock Adjustment", parent_account=cogs_account_name, company=company_name, account_type="Stock Adjustment").insert(ignore_permissions=True)
        company_doc.stock_adjustment_account = stock_adj_account_name
        current_asset_account = f"Activos Corrientes - {abbr}"
        if not frappe.db.exists("Account", current_asset_account):
            current_asset_account = asset_root
        if not frappe.db.exists("Account", {"account_name": "Caja General", "company": company_name}):
            frappe.new_doc("Account", account_name="Caja General", parent_account=current_asset_account, company=company_name, account_type="Cash").insert(ignore_permissions=True)

        company_doc.save(ignore_permissions=True)
        
        if not frappe.db.exists("Warehouse", {"warehouse_name": f"Bodega tienda - {abbr}"}):
            frappe.new_doc("Warehouse", warehouse_name=f"Bodega tienda - {abbr}", company=company_name).insert(ignore_permissions=True)
        if not frappe.db.exists("Item Group", data.get("default_item_group")):
            frappe.new_doc("Item Group", item_group_name=data.get("default_item_group"), is_group=1).insert(ignore_permissions=True)
        if not frappe.db.exists("Customer Group", data.get("default_customer_group")):
            frappe.new_doc("Customer Group", customer_group_name=data.get("default_customer_group")).insert(ignore_permissions=True)
        if not frappe.db.exists("Supplier Group", data.get("default_supplier_group")):
            frappe.new_doc("Supplier Group", supplier_group_name=data.get("default_supplier_group")).insert(ignore_permissions=True)
        if not frappe.db.exists("UOM", data.get("default_uom")):
            frappe.new_doc("UOM", uom_name=data.get("default_uom")).insert(ignore_permissions=True)

        # --- Creación de Usuario y Credenciales (LÓGICA CORREGIDA) ---
        api_key, api_secret = None, None
        if not frappe.db.exists("User", seller_email):
            # 1. Crear el usuario
            user = frappe.new_doc("User")
            user.update({"email": seller_email, "first_name": data.get("user_first_name"), "last_name": data.get("user_last_name"), "send_welcome_email": 0})
            user.add_roles("Accounts User", "Purchase User")
            user.save(ignore_permissions=True) # Guardar el usuario primero

            # 2. Generar las claves manualmente
            api_key = secrets.token_hex(16)
            api_secret = secrets.token_hex(16) # Este es el secreto en texto plano que devolveremos
            
            # 3. Guardar las claves en el documento del usuario (el secreto se encripta)
            user.api_key = api_key
            user.api_secret = password.encrypt(api_secret)
            user.save(ignore_permissions=True)
        else:
            keys = frappe.db.get_value("User", seller_email, ["api_key"], as_dict=True)
            api_key = keys.api_key if keys else None
            api_secret = "SECRET_OCULTO (El usuario ya existe, use las credenciales existentes)"

        frappe.db.commit()

        return {
            "status": "SUCCESS",
            "message": f"Environment for company '{company_name}' and user '{seller_email}' is ready.",
            "new_user_credentials": {
                "api_key": api_key,
                "api_secret": api_secret
            }
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Company & User Setup Failed", message=frappe.get_traceback())
        frappe.throw(f"An error occurred during setup: {str(e)}")


# ==============================================================================
# ENDPOINT 2: CREATE SALES INVOICE AND PAYMENT (Sin cambios)
# ==============================================================================
@frappe.whitelist()
def create_sales_invoice_with_payment():
    data = frappe.local.form_dict
    try:
        company_name = frappe.db.get_value("Company", {"abbr": data.get("company_abbr")}, "name")
        if not company_name:
            frappe.throw(f"Company with abbreviation '{data.get('company_abbr')}' not found.")
        company_doc = frappe.get_doc("Company", company_name)
        default_item_group = frappe.db.get_value("Item Group", {"item_group_name": "Todos los grupos de productos"})
        default_customer_group = frappe.db.get_value("Customer Group", {"customer_group_name": "Individual"})
        default_supplier_group = frappe.db.get_value("Supplier Group", {"supplier_group_name": "Todos los grupos de proveedores"})
        default_uom = frappe.db.get_value("UOM", {"uom_name": "Unidad"})
        if not all([default_item_group, default_customer_group, default_supplier_group, default_uom]):
            frappe.throw("Default master data (Groups, UOM) not found. Please run the setup script.")
        if not frappe.db.exists("Customer", data.get("customer_name")):
            customer = frappe.new_doc("Customer")
            customer.update({"customer_name": data.get("customer_name"), "customer_group": default_customer_group})
            customer.append("accounts", {"company": company_name, "account": company_doc.default_receivable_account})
            customer.insert(ignore_permissions=True)
        if not frappe.db.exists("Supplier", data.get("supplier_name")):
            frappe.new_doc("Supplier", supplier_name=data.get("supplier_name"), supplier_group=default_supplier_group).insert(ignore_permissions=True)
        if not frappe.db.exists("Item", data.get("item_code")):
            frappe.new_doc("Item", item_code=data.get("item_code"), item_name=data.get("item_name"), item_group=default_item_group, stock_uom=default_uom, is_stock_item=1).insert(ignore_permissions=True)
        warehouse_name = f"Bodega tienda - {data.get('company_abbr')}"
        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.stock_entry_type = "Material Receipt"
        stock_entry.company = company_name
        stock_entry.append("items", {"item_code": data.get("item_code"), "qty": data.get("item_qty", 1) * 10, "t_warehouse": warehouse_name, "basic_rate": data.get("item_rate", 1) * 0.5})
        stock_entry.submit()
        si = frappe.new_doc("Sales Invoice")
        si.customer = data.get("customer_name")
        si.company = company_name
        si.posting_date = getdate(data.get("posting_date", nowdate()))
        si.update_stock = 1
        si.append("items", {"item_code": data.get("item_code"), "qty": data.get("item_qty"), "rate": data.get("item_rate"), "warehouse": warehouse_name, "income_account": company_doc.default_income_account})
        si.submit()
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
        frappe.db.commit()
        return { "status": "SUCCESS", "message": f"Invoice cycle created successfully by user {frappe.session.user}.", "sales_invoice": si.name, "payment_entry": pe.name }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Sales Invoice Cycle Failed", message=frappe.get_traceback())
        frappe.throw(f"An error occurred during the invoice cycle: {str(e)}")
