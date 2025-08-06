import frappe
import subprocess
import secrets
from frappe.utils.password import update_password, set_encrypted_password
import os
from frappe.utils.file_manager import get_file_path
from frappe import _
from frappe.utils import getdate, nowdate

# ==============================================================================
# SCRIPT 1: SETUP COMPANY ENVIRONMENT
# ==============================================================================
@frappe.whitelist()
def setup_company_environment():
    data = frappe.local.form_dict

    try:
        company_name = data.get("company_name")
        abbr = data.get("company_abbr")

        # 1. Create Company
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

        # 2. Setup Accounts
        asset_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Asset", "is_group": 1})
        income_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Income", "is_group": 1})
        expense_root = frappe.db.get_value("Account", {"company": company_name, "root_type": "Expense", "is_group": 1})
        
        # ... (Otras creaciones de cuentas se mantienen igual) ...
        receivable_account_name = f"Deudores - {abbr}"
        if not frappe.db.exists("Account", receivable_account_name):
            acc = frappe.new_doc("Account")
            acc.update({"account_name": "Deudores", "parent_account": asset_root, "company": company_name, "account_type": "Receivable"})
            acc.insert(ignore_permissions=True)
        company_doc.default_receivable_account = receivable_account_name
        
        income_account_name = f"Ventas - {abbr}"
        if not frappe.db.exists("Account", income_account_name):
            acc = frappe.new_doc("Account")
            acc.update({"account_name": "Ventas", "parent_account": income_root, "company": company_name, "account_type": "Income Account"})
            acc.insert(ignore_permissions=True)
        company_doc.default_income_account = income_account_name
        
        cogs_account_name = f"Costos de los bienes vendidos - {abbr}"
        if not frappe.db.exists("Account", cogs_account_name):
            acc = frappe.new_doc("Account")
            acc.update({"account_name": "Costos de los bienes vendidos", "parent_account": expense_root, "company": company_name, "is_group": 1, "account_type": "Cost of Goods Sold"})
            acc.insert(ignore_permissions=True)
        
        stock_adj_account_name = f"Stock Adjustment - {abbr}"
        if not frappe.db.exists("Account", stock_adj_account_name):
            acc = frappe.new_doc("Account")
            acc.update({"account_name": "Stock Adjustment", "parent_account": cogs_account_name, "company": company_name, "account_type": "Stock Adjustment"})
            acc.insert(ignore_permissions=True)
        company_doc.stock_adjustment_account = stock_adj_account_name
        
        current_asset_account = f"Activos Corrientes - {abbr}"
        if not frappe.db.exists("Account", current_asset_account):
            current_asset_account = asset_root
        if not frappe.db.exists("Account", {"account_name": "Caja General", "company": company_name}):
            acc = frappe.new_doc("Account")
            acc.update({"account_name": "Caja General", "parent_account": current_asset_account, "company": company_name, "account_type": "Cash"})
            acc.insert(ignore_permissions=True)

        # --- NUEVA SECCIÓN: Cuenta de Inventario por Defecto ---
        stock_asset_account_name = f"Activos de inventario - {abbr}"
        if not frappe.db.exists("Account", stock_asset_account_name):
            acc = frappe.new_doc("Account")
            acc.update({"account_name": "Activos de inventario", "parent_account": asset_root, "company": company_name, "account_type": "Stock"})
            acc.insert(ignore_permissions=True)
        company_doc.default_inventory_account = stock_asset_account_name
        # --- FIN DE LA NUEVA SECCIÓN ---

        company_doc.save(ignore_permissions=True)

        # 3. Create Default Groups
        if not frappe.db.exists("Warehouse", {"warehouse_name": f"Bodega tienda - {abbr}"}):
            wh = frappe.new_doc("Warehouse")
            wh.update({"warehouse_name": f"Bodega tienda - {abbr}", "company": company_name})
            wh.insert(ignore_permissions=True)
        if not frappe.db.exists("Item Group", "Todos los grupos de productos"):
            ig = frappe.new_doc("Item Group")
            ig.update({"item_group_name": "Todos los grupos de productos", "is_group": 1})
            ig.insert(ignore_permissions=True)
        if not frappe.db.exists("Customer Group", "Individual"):
            cg = frappe.new_doc("Customer Group")
            cg.update({"customer_group_name": "Individual"})
            cg.insert(ignore_permissions=True)
        if not frappe.db.exists("Supplier Group", "Todos los grupos de proveedores"):
            sg = frappe.new_doc("Supplier Group")
            sg.update({"supplier_group_name": "Todos los grupos de proveedores"})
            sg.insert(ignore_permissions=True)
        if not frappe.db.exists("UOM", "Unidad"):
            uom = frappe.new_doc("UOM")
            uom.update({"uom_name": "Unidad"})
            uom.insert(ignore_permissions=True)
        
        frappe.db.commit()
        return {"status": "success", "message": f"Environment for company '{company_name}' configured successfully."}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Company Environment Setup Failed", message=frappe.get_traceback())
        frappe.throw(f"An error occurred during company setup: {str(e)}")

# ==============================================================================
# SCRIPT 2: CREATE TRANSACTIONAL INVOICE
# ==============================================================================
@frappe.whitelist()
def create_transactional_invoice():
    data = frappe.local.form_dict
    
    try:
        company_name = data.get("company_name")
        if not frappe.db.exists("Company", company_name):
            frappe.throw(f"Company '{company_name}' not found. Please run the setup script first.")
        
        company_doc = frappe.get_doc("Company", company_name)
        
        # Ensure User, Customer, Supplier, Item exist
        if not frappe.db.exists("User", data.get("user_email")):
            user = frappe.new_doc("User")
            user.update({"email": data.get("user_email"), "first_name": data.get("user_first_name"), "last_name": data.get("user_last_name"), "send_welcome_email": 0})
            user.add_roles("Purchase User", "Accounts User")
            user.insert(ignore_permissions=True)

        if not frappe.db.exists("Customer", data.get("customer_name")):
            customer = frappe.new_doc("Customer")
            customer.update({"customer_name": data.get("customer_name"), "customer_group": data.get("customer_group")})
            customer.append("accounts", {"company": company_name, "account": company_doc.default_receivable_account})
            customer.insert(ignore_permissions=True)
        
        if not frappe.db.exists("Supplier", data.get("supplier_name")):
            frappe.new_doc("Supplier", supplier_name=data.get("supplier_name"), supplier_group=data.get("supplier_group")).insert(ignore_permissions=True)

        if not frappe.db.exists("Item", data.get("item_code")):
            frappe.new_doc("Item", item_code=data.get("item_code"), item_name=data.get("item_name"), item_group=data.get("item_group"), stock_uom=data.get("uom_name"), is_stock_item=1).insert(ignore_permissions=True)

        # Create transactions
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
        sales_invoice_name = si.name

        cash_account = frappe.db.get_value("Account", {"account_name": "Caja General", "company": company_name})
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = data.get("customer_name")
        pe.company = company_name
        pe.paid_amount = si.grand_total
        pe.received_amount = si.grand_total
        pe.paid_to = cash_account
        pe.append("references", {"reference_doctype": "Sales Invoice", "reference_name": sales_invoice_name, "total_amount": si.grand_total, "outstanding_amount": si.grand_total, "allocated_amount": si.grand_total})
        pe.submit()

        frappe.db.commit()

        return {"status": "success", "message": "Invoice created and paid successfully.", "sales_invoice": sales_invoice_name, "payment_entry": pe.name}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Transactional Invoice Creation Failed", message=frappe.get_traceback())
        frappe.throw(f"An error occurred during invoice creation: {str(e)}")
        frappe.throw(f"An error occurred during invoice creation: {str(e)}")
