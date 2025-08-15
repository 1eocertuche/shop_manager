import frappe
import json # <--- IMPORT THE JSON LIBRARY
from frappe.utils import getdate, nowdate
import secrets

# ==============================================================================
# UTILITY FUNCTION TO GET COMPANY NAME BY ABBREVIATION
# ==============================================================================
def get_company_by_abbr(abbr):
    if not abbr:
        frappe.throw("Company Abbreviation is required.")
    company_name = frappe.db.get_value("Company", {"abbr": abbr}, "name")
    if not company_name:
        frappe.throw(f"Company with abbreviation '{abbr}' not found.")
    return company_name

# ==============================================================================
# ENDPOINT 1: SETUP COMPANY AND USER ENVIRONMENT (FINAL CORRECTED VERSION)
# ==============================================================================
@frappe.whitelist()
def setup_company_and_user():
    # === THE FINAL BUG FIX ===
    # Read the raw request data and parse it as JSON
    data = json.loads(frappe.request.data)
    
    try:
        company_name = data.get("company_name")
        abbr = data.get("company_abbr")
        user_email = data.get("user_email")

        # Part 1: Create Company if it doesn't exist
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

        # ... (The rest of the function remains unchanged)
        
        # Part 2: Discover Root Accounts
        asset_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Asset", "is_group": 1})
        income_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Income", "is_group": 1})
        expense_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Expense", "is_group": 1})
        payable_root = frappe.db.get_value("Account", {"company": company_name, "account_type": "Payable", "is_group": 1})

        # Part 3: Setup Essential Accounts
        receivable_account_name = f"Deudores - {abbr}"
        if not frappe.db.exists("Account", receivable_account_name):
            frappe.new_doc("Account", {"account_name": "Deudores", "parent_account": asset_root, "company": company_name, "account_type": "Receivable"}).insert(ignore_permissions=True)
        company_doc.default_receivable_account = receivable_account_name
        
        income_account_name = f"Ventas - {abbr}"
        if not frappe.db.exists("Account", income_account_name):
            frappe.new_doc("Account", {"account_name": "Ventas", "parent_account": income_root, "company": company_name, "account_type": "Income Account"}).insert(ignore_permissions=True)
        company_doc.default_income_account = income_account_name
        
        stock_asset_account_name = f"Inventario de Mercancías - {abbr}"
        if not frappe.db.exists("Account", stock_asset_account_name):
            frappe.new_doc("Account", {"account_name": "Inventario de Mercancías", "parent_account": asset_root, "company": company_name, "account_type": "Stock"}).insert(ignore_permissions=True)
        company_doc.default_inventory_account = stock_asset_account_name
        
        cogs_account_name = f"Costos de los bienes vendidos - {abbr}"
        if not frappe.db.exists("Account", cogs_account_name):
            frappe.new_doc("Account", {"account_name": "Costos de los bienes vendidos", "parent_account": expense_root, "company": company_name, "is_group": 1, "account_type": "Cost of Goods Sold"}).insert(ignore_permissions=True)
        stock_adj_account_name = f"Stock Adjustment - {abbr}"
        if not frappe.db.exists("Account", stock_adj_account_name):
            frappe.new_doc("Account", {"account_name": "Stock Adjustment", "parent_account": cogs_account_name, "company": company_name, "account_type": "Stock Adjustment"}).insert(ignore_permissions=True)
        company_doc.stock_adjustment_account = stock_adj_account_name

        srbnb_account_name = f"Activo recibido pero no facturado - {abbr}"
        if not frappe.db.exists("Account", srbnb_account_name):
            frappe.new_doc("Account", {"account_name": "Activo recibido pero no facturado", "parent_account": payable_root, "company": company_name, "account_type": "Stock Received But Not Billed"}).insert(ignore_permissions=True)
        company_doc.stock_received_but_not_billed = srbnb_account_name

        current_asset_account = frappe.db.get_value("Account", {"account_name": f"Activos Corrientes - {abbr}"}) or asset_root
        if not frappe.db.exists("Account", {"account_name": "Caja General", "company": company_name}):
            frappe.new_doc("Account", {"account_name": "Caja General", "parent_account": current_asset_account, "company": company_name, "account_type": "Cash"}).insert(ignore_permissions=True)

        company_doc.save(ignore_permissions=True)

        # Part 4: Setup Warehouses and Default Groups
        if not frappe.db.exists("Warehouse", f"Almacén Principal - {abbr}"):
            frappe.new_doc("Warehouse", {"warehouse_name": f"Almacén Principal - {abbr}", "company": company_name, "is_group": 0}).insert(ignore_permissions=True)
        if not frappe.db.exists("Item Group", data.get("default_item_group")):
            frappe.new_doc("Item Group", {"item_group_name": data.get("default_item_group"), "is_group": 1}).insert(ignore_permissions=True)
        if not frappe.db.exists("Customer Group", data.get("default_customer_group")):
            frappe.new_doc("Customer Group", {"customer_group_name": data.get("default_customer_group")}).insert(ignore_permissions=True)
        if not frappe.db.exists("Supplier Group", data.get("default_supplier_group")):
            frappe.new_doc("Supplier Group", {"supplier_group_name": data.get("default_supplier_group")}).insert(ignore_permissions=True)
        if not frappe.db.exists("UOM", data.get("default_uom")):
            frappe.new_doc("UOM", {"uom_name": data.get("default_uom")}).insert(ignore_permissions=True)

        # Part 5: Create User and API Credentials
        api_key, api_secret = None, None
        if not frappe.db.exists("User", user_email):
            user = frappe.new_doc("User")
            user.update({"email": user_email, "first_name": data.get("user_first_name"), "last_name": data.get("user_last_name"), "send_welcome_email": 0})
            user.add_roles("Accounts User", "Purchase User", "Stock User", "Sales User")
            user.save(ignore_permissions=True)
            
            api_key = secrets.token_hex(16)
            api_secret = secrets.token_hex(16)
            user.api_key = api_key
            user.set("api_secret", api_secret)
            user.save(ignore_permissions=True)
        else:
            user = frappe.get_doc("User", user_email)
            user.add_roles("Accounts User", "Purchase User", "Stock User", "Sales User")
            user.save(ignore_permissions=True)
            api_key = user.api_key
            api_secret = "SECRET_OCULTO (El usuario ya existe, use las credenciales existentes)"

        frappe.db.commit()
        return {"status": "SUCCESS", "message": f"Environment for company '{company_name}' and user '{user_email}' is ready.", "new_user_credentials": {"api_key": api_key, "api_secret": api_secret}}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Company & User Setup Failed", message=frappe.get_traceback())
        frappe.throw(f"An error occurred during setup: {str(e)}")


# ==============================================================================
# ENDPOINT 2: CREATE PURCHASE INVOICE (FINAL CORRECTED VERSION)
# ==============================================================================
@frappe.whitelist()
def create_purchase_invoice():
    # === THE FINAL BUG FIX ===
    data = json.loads(frappe.request.data)
    
    try:
        company_name = get_company_by_abbr(data.get("company_abbr"))

        # Idempotently create Supplier and Item
        if not frappe.db.exists("Supplier", data.get("supplier_name")):
            frappe.new_doc("Supplier", {"supplier_name": data.get("supplier_name"), "supplier_group": data.get("supplier_group")}).insert(ignore_permissions=True)
        if not frappe.db.exists("Item", data.get("item_code")):
            frappe.new_doc("Item", {"item_code": data.get("item_code"), "item_name": data.get("item_name"), "item_group": data.get("item_group"), "stock_uom": data.get("uom_name"), "is_stock_item": 1}).insert(ignore_permissions=True)

        warehouse_name = f"Almacén Principal - {data.get('company_abbr')}"

        # Create and submit the Purchase Invoice
        pi = frappe.new_doc("Purchase Invoice")
        pi.company = company_name
        pi.supplier = data.get("supplier_name")
        pi.posting_date = getdate(data.get("posting_date", nowdate()))
        pi.due_date = getdate(data.get("due_date"))
        pi.update_stock = 1
        pi.set_posting_time = 1
        pi.append("items", {
            "item_code": data.get("item_code"),
            "qty": data.get("item_qty"),
            "rate": data.get("item_rate"),
            "warehouse": warehouse_name,
        })
        pi.submit()

        frappe.db.commit()
        return {
            "status": "SUCCESS",
            "message": "Purchase Invoice created and submitted successfully.",
            "purchase_invoice": pi.name
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Purchase Invoice Creation Failed", message=frappe.get_traceback())
        frappe.throw(f"An error occurred during purchase invoice creation: {str(e)}")
