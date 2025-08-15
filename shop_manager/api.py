import frappe
import json
from frappe.utils import getdate, nowdate
import secrets

# ==============================================================================
# ENDPOINT 1: SETUP COMPANY AND USER (FINAL SIMPLIFIED VERSION)
# This function now accepts named arguments, which is the most reliable method.
# ==============================================================================
@frappe.whitelist()
def setup_company_and_user(company_name, company_abbr, user_email, user_first_name, user_last_name, 
                           default_item_group, default_customer_group, default_supplier_group, default_uom):
    try:
        # Part 1: Create Company if it doesn't exist
        if not frappe.db.exists("Company", company_name):
            company = frappe.new_doc("Company")
            company.update({
                "company_name": company_name, 
                "abbr": company_abbr, 
                "country": "Colombia", 
                "default_currency": "COP", 
                "chart_of_accounts": "Colombia PUC Simple"
            })
            company.insert(ignore_permissions=True)
        
        company_doc = frappe.get_doc("Company", company_name)
        
        # Part 2: Discover Root Accounts
        asset_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Asset", "is_group": 1})
        income_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Income", "is_group": 1})
        expense_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Expense", "is_group": 1})
        payable_root = frappe.db.get_value("Account", {"company": company_name, "account_type": "Payable", "is_group": 1})

        # Part 3: Setup Essential Accounts
        receivable_account_name = f"Deudores - {company_abbr}"
        if not frappe.db.exists("Account", receivable_account_name):
            frappe.new_doc("Account", {"account_name": "Deudores", "parent_account": asset_root, "company": company_name, "account_type": "Receivable"}).insert(ignore_permissions=True)
        company_doc.default_receivable_account = receivable_account_name
        
        income_account_name = f"Ventas - {company_abbr}"
        if not frappe.db.exists("Account", income_account_name):
            frappe.new_doc("Account", {"account_name": "Ventas", "parent_account": income_root, "company": company_name, "account_type": "Income Account"}).insert(ignore_permissions=True)
        company_doc.default_income_account = income_account_name
        
        stock_asset_account_name = f"Inventario de Mercancías - {company_abbr}"
        if not frappe.db.exists("Account", stock_asset_account_name):
            frappe.new_doc("Account", {"account_name": "Inventario de Mercancías", "parent_account": asset_root, "company": company_name, "account_type": "Stock"}).insert(ignore_permissions=True)
        company_doc.default_inventory_account = stock_asset_account_name
        
        srbnb_account_name = f"Activo recibido pero no facturado - {company_abbr}"
        if not frappe.db.exists("Account", srbnb_account_name):
            frappe.new_doc("Account", {"account_name": "Activo recibido pero no facturado", "parent_account": payable_root, "company": company_name, "account_type": "Stock Received But Not Billed"}).insert(ignore_permissions=True)
        company_doc.stock_received_but_not_billed = srbnb_account_name

        company_doc.save(ignore_permissions=True)

        # Part 4: Setup Warehouses and Default Groups
        if not frappe.db.exists("Warehouse", f"Almacén Principal - {company_abbr}"):
            frappe.new_doc("Warehouse", {"warehouse_name": f"Almacén Principal - {company_abbr}", "company": company_name, "is_group": 0}).insert(ignore_permissions=True)
        if not frappe.db.exists("Item Group", default_item_group):
            frappe.new_doc("Item Group", {"item_group_name": default_item_group, "is_group": 1}).insert(ignore_permissions=True)
        if not frappe.db.exists("Customer Group", default_customer_group):
            frappe.new_doc("Customer Group", {"customer_group_name": default_customer_group}).insert(ignore_permissions=True)
        if not frappe.db.exists("Supplier Group", default_supplier_group):
            frappe.new_doc("Supplier Group", {"supplier_group_name": default_supplier_group}).insert(ignore_permissions=True)
        if not frappe.db.exists("UOM", default_uom):
            frappe.new_doc("UOM", {"uom_name": default_uom}).insert(ignore_permissions=True)

        # Part 5: Create User and API Credentials
        if not frappe.db.exists("User", user_email):
            user = frappe.new_doc("User")
            user.update({"email": user_email, "first_name": user_first_name, "last_name": user_last_name, "send_welcome_email": 0})
            user.add_roles("Accounts User", "Purchase User", "Stock User", "Sales User")
            user.save(ignore_permissions=True)
            
            api_key = secrets.token_hex(16)
            api_secret = secrets.token_hex(16)
            user.api_key = api_key
            user.set("api_secret", api_secret)
            user.save(ignore_permissions=True)
        
        frappe.db.commit()
        user_keys = frappe.db.get_value("User", user_email, ["api_key", "api_secret"], as_dict=True)
        return {"status": "SUCCESS", "message": f"Environment for company '{company_name}' and user '{user_email}' is ready.", "new_user_credentials": user_keys}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Company & User Setup Failed", message=frappe.get_traceback())
        frappe.throw(f"An error occurred during setup: {str(e)}")


# ==============================================================================
# ENDPOINT 2: CREATE PURCHASE INVOICE (FINAL SIMPLIFIED VERSION)
# This function also uses named arguments for reliability.
# ==============================================================================
@frappe.whitelist()
def create_purchase_invoice(company_abbr, supplier_name, supplier_group, item_code, item_name, item_group, uom_name, item_qty, item_rate, posting_date, due_date):
    try:
        company_name = frappe.db.get_value("Company", {"abbr": company_abbr}, "name")
        if not company_name:
            frappe.throw(f"Company with abbreviation '{company_abbr}' not found.")

        # Idempotently create Supplier and Item
        if not frappe.db.exists("Supplier", supplier_name):
            frappe.new_doc("Supplier", {"supplier_name": supplier_name, "supplier_group": supplier_group}).insert(ignore_permissions=True)
        if not frappe.db.exists("Item", item_code):
            frappe.new_doc("Item", {"item_code": item_code, "item_name": item_name, "item_group": item_group, "stock_uom": uom_name, "is_stock_item": 1}).insert(ignore_permissions=True)

        warehouse_name = f"Almacén Principal - {company_abbr}"

        # Create and submit the Purchase Invoice
        pi = frappe.new_doc("Purchase Invoice")
        pi.company = company_name
        pi.supplier = supplier_name
        pi.posting_date = getdate(posting_date)
        pi.due_date = getdate(due_date)
        pi.update_stock = 1
        pi.set_posting_time = 1
        pi.append("items", {
            "item_code": item_code,
            "qty": item_qty,
            "rate": item_rate,
            "warehouse": warehouse_name,
        })
        pi.submit()

        frappe.db.commit()
        return { "status": "SUCCESS", "message": "Purchase Invoice created and submitted successfully.", "purchase_invoice": pi.name }
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Purchase Invoice Creation Failed", message=frappe.get_traceback())
        # The syntax error was here. The "```" has been removed.
        frappe.throw(f"An error occurred during purchase invoice creation: {str(e)}")
