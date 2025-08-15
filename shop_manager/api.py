import frappe
from frappe.utils import getdate, nowdate
import secrets

# ==============================================================================
# ENDPOINT 1: SETUP COMPANY AND USER (FINAL IDEMPOTENT VERSION)
# This version correctly handles existing users to prevent duplicate entry errors.
# ==============================================================================
@frappe.whitelist()
def setup_company_and_user():
    data = frappe.local.form_dict
    
    try:
        company_name = data.get("company_name")
        abbr = data.get("company_abbr")
        user_email = data.get("user_email")

        # --- Setup de la Compañía y Cuentas ---
        if not frappe.db.exists("Company", company_name):
            company = frappe.new_doc("Company")
            company.company_name = company_name
            company.abbr = abbr
            company.country = "Colombia"
            company.default_currency = "COP"
            company.chart_of_accounts = "Colombia PUC Simple"
            company.insert(ignore_permissions=True)
        
        company_doc = frappe.get_doc("Company", company_name)
        
        asset_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Asset", "is_group": 1})
        income_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Income", "is_group": 1})
        payable_root = frappe.db.get_value("Account", {"company": company_name, "account_type": "Payable", "is_group": 1})

        receivable_account_name = f"Deudores - {abbr}"
        if not frappe.db.exists("Account", receivable_account_name):
            acc = frappe.new_doc("Account")
            acc.account_name = "Deudores"
            acc.parent_account = asset_root
            acc.company = company_name
            acc.account_type = "Receivable"
            acc.insert(ignore_permissions=True)
        company_doc.default_receivable_account = receivable_account_name
        
        income_account_name = f"Ventas - {abbr}"
        if not frappe.db.exists("Account", income_account_name):
            acc = frappe.new_doc("Account")
            acc.account_name = "Ventas"
            acc.parent_account = income_root
            acc.company = company_name
            acc.account_type = "Income Account"
            acc.insert(ignore_permissions=True)
        company_doc.default_income_account = income_account_name
        
        stock_asset_account_name = f"Activos de inventario - {abbr}"
        if not frappe.db.exists("Account", stock_asset_account_name):
            acc = frappe.new_doc("Account")
            acc.account_name = "Activos de inventario"
            acc.parent_account = asset_root
            acc.company = company_name
            acc.account_type = "Stock"
            acc.insert(ignore_permissions=True)
        company_doc.default_inventory_account = stock_asset_account_name
        
        srbnb_account_name = f"Activo recibido pero no facturado - {abbr}"
        if not frappe.db.exists("Account", srbnb_account_name):
            acc = frappe.new_doc("Account")
            acc.account_name = "Activo recibido pero no facturado"
            acc.parent_account = payable_root
            acc.company = company_name
            acc.account_type = "Stock Received But Not Billed"
            acc.insert(ignore_permissions=True)
        company_doc.stock_received_but_not_billed = srbnb_account_name
        
        if not frappe.db.exists("Account", {"account_name": "Caja General", "company": company_name}):
            acc = frappe.new_doc("Account")
            acc.account_name = "Caja General"
            acc.parent_account = asset_root
            acc.company = company_name
            acc.account_type = "Cash"
            acc.insert(ignore_permissions=True)
            
        company_doc.save(ignore_permissions=True)
        
        if not frappe.db.exists("Warehouse", f"Bodega tienda - {abbr}"):
            wh = frappe.new_doc("Warehouse")
            wh.warehouse_name = f"Bodega tienda - {abbr}"
            wh.company = company_name
            wh.insert(ignore_permissions=True)
            
        if not frappe.db.exists("Warehouse", f"Almacén Principal - {abbr}"):
            wh = frappe.new_doc("Warehouse")
            wh.warehouse_name = f"Almacén Principal - {abbr}"
            wh.company = company_name
            wh.insert(ignore_permissions=True)
            
        if not frappe.db.exists("Item Group", data.get("default_item_group")):
            ig = frappe.new_doc("Item Group")
            ig.item_group_name = data.get("default_item_group")
            ig.is_group = 1
            ig.insert(ignore_permissions=True)
            
        if not frappe.db.exists("Customer Group", data.get("default_customer_group")):
            cg = frappe.new_doc("Customer Group")
            cg.customer_group_name = data.get("default_customer_group")
            cg.insert(ignore_permissions=True)
            
        if not frappe.db.exists("Supplier Group", data.get("default_supplier_group")):
            sg = frappe.new_doc("Supplier Group")
            sg.supplier_group_name = data.get("default_supplier_group")
            sg.insert(ignore_permissions=True)
            
        if not frappe.db.exists("UOM", data.get("default_uom")):
            uom = frappe.new_doc("UOM")
            uom.uom_name = data.get("default_uom")
            uom.insert(ignore_permissions=True)
            
        # --- Creación de Usuario y Credenciales (FINAL ROBUST VERSION) ---
        if not frappe.db.exists("User", user_email):
            # Create the user if they do not exist
            user = frappe.new_doc("User")
            user.email = user_email
            user.first_name = data.get("user_first_name")
            user.last_name = data.get("user_last_name")
            user.send_welcome_email = 0
            user.add_roles("Accounts User", "Purchase User", "Stock User", "Sales User")
            user.insert(ignore_permissions=True)
            
            # Generate new API keys for the new user
            api_key = secrets.token_hex(16)
            api_secret = secrets.token_hex(16)
            user.api_key = api_key
            user.set("api_secret", api_secret)
            user.save(ignore_permissions=True)
        else:
            # If the user already exists, get them and ensure their roles are correct
            user = frappe.get_doc("User", user_email)
            user.add_roles("Accounts User", "Purchase User", "Stock User", "Sales User")
            user.save(ignore_permissions=True)
            
        frappe.db.commit()
        # Always return the latest API keys for this user
        user_keys = frappe.db.get_value("User", user_email, ["api_key", "api_secret"], as_dict=True)
        return {"status": "SUCCESS", "message": f"Environment for company '{company_name}' and user '{user_email}' is ready.", "new_user_credentials": user_keys}
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Company & User Setup Failed", message=frappe.get_traceback())
        frappe.throw(f"An error occurred during setup: {str(e)}")

# ==============================================================================
# ENDPOINT 2: CREATE SALES INVOICE AND PAYMENT (Preserved and Corrected)
# ==============================================================================
@frappe.whitelist()
def create_sales_invoice_with_payment():
    data = frappe.local.form_dict
    try:
        company_name = frappe.db.get_value("Company", {"abbr": data.get("company_abbr")}, "name")
        if not company_name:
            frappe.throw(f"Company with abbreviation '{data.get('company_abbr')}' not found.")
            
        company_doc = frappe.get_doc("Company", company_name)
        
        if not frappe.db.exists("Customer", data.get("customer_name")):
            customer = frappe.new_doc("Customer")
            customer.customer_name = data.get("customer_name")
            customer.customer_group = data.get("customer_group")
            customer.insert(ignore_permissions=True)
            
        if not frappe.db.exists("Item", data.get("item_code")):
            item = frappe.new_doc("Item")
            item.item_code = data.get("item_code")
            item.item_name = data.get("item_name")
            item.item_group = data.get("item_group")
            item.stock_uom = data.get("uom_name")
            item.is_stock_item = 1
            item.insert(ignore_permissions=True)
            
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
        pe.append("references", {"reference_doctype": "Sales Invoice", "reference_name": si.name, "allocated_am
