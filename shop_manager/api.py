import frappe
import subprocess
import secrets
from frappe.utils.password import update_password, set_encrypted_password
import os
from frappe.utils.file_manager import get_file_path
from frappe import _

@frappe.whitelist()
def save_api_code(api_code):
    """
    Save the API code and trigger bench commands to apply changes
    """
    # Check if user has permission to edit API
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted. You need the 'System Manager' role.", frappe.PermissionError)
    
    try:
        # Get the path to the api.py file
        app_path = frappe.get_app_path('shop_manager')
        api_file_path = os.path.join(app_path, 'api.py')
        
        # Create a backup of the original file
        backup_path = os.path.join(app_path, 'api.py.backup')
        if os.path.exists(api_file_path):
            with open(api_file_path, 'r') as original_file:
                with open(backup_path, 'w') as backup_file:
                    backup_file.write(original_file.read())
        
        # Write the new code to the file
        with open(api_file_path, 'w') as file:
            file.write(api_code)
        
        # Run bench commands in the background
        frappe.enqueue('shop_manager.api.apply_api_changes', queue='long')
        
        return {"status": "success", "message": "API code saved successfully. Changes will be applied shortly."}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "save_api_code Error")
        frappe.throw(f"An error occurred while saving API code: {str(e)}")

@frappe.whitelist()
def apply_api_changes():
    """
    Apply API changes by running bench commands
    """
    try:
        # Change to the frappe-bench directory
        bench_path = os.path.join(os.path.expanduser('~'), 'frappe-bench')
        
        # Run bench commands
        subprocess.check_call(['bench', 'restart'], cwd=bench_path)
        
        # Log the successful restart
        frappe.log_error("API changes applied successfully", "API Editor")
        
        return {"status": "success", "message": "API changes applied successfully."}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "apply_api_changes Error")
        return {"status": "error", "message": str(e)}



#create a valid cash account for your company
@frappe.whitelist()
def setup_cash_account(company_name, company_abbr):
    """
    Ensures a valid 'Cash' type account exists for the company,
    which is required for making Payment Entries.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted. You need the 'System Manager' role.", frappe.PermissionError)

    if not frappe.db.exists("Company", company_name):
        frappe.throw(f"Company '{company_name}' does not exist.")

    try:
        # Step 1: Discover the correct "Current Assets" parent account for this company.
        # The name is created by the Chart of Accounts template.
        parent_account = f"Activos Corrientes - {company_abbr}"
        if not frappe.db.exists("Account", parent_account):
            # As a fallback, find the root asset account if the specific one isn't there.
             parent_account = frappe.db.get_value("Account", {"company": company_name, "root_type": "Asset", "is_group": 1})
             if not parent_account:
                 frappe.throw(f"Could not find any suitable asset accounts for {company_name}.")


        # Step 2: Define and create the new "Cash" account if it doesn't exist.
        cash_account_name = f"Caja General - {company_abbr}"
        if not frappe.db.exists("Account", {"account_name": cash_account_name, "company": company_name}):
            cash_doc = frappe.new_doc("Account")
            cash_doc.company = company_name
            cash_doc.account_name = "Caja General"
            cash_doc.parent_account = parent_account
            cash_doc.is_group = 0
            cash_doc.account_type = "Cash"  # This is the critical field!
            cash_doc.insert(ignore_permissions=True)
            frappe.db.commit()

        return {
            "status": "success",
            "message": f"Cash account '{cash_account_name}' is configured for {company_name}.",
            "cash_account_name": cash_account_name
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "setup_cash_account Error")
        frappe.throw(f"An error occurred during cash account setup: {str(e)}")



# Creates the required account hierarchy for stock transactions

@frappe.whitelist()
def setup_company_accounts_for_stock(company_name, company_abbr):
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted. You need the 'System Manager' role.", frappe.PermissionError)

    if not frappe.db.exists("Company", company_name):
        frappe.throw(f"Company '{company_name}' does not exist.")

    try:
        # --- THE CRITICAL FIX STARTS HERE ---
        # Discover the root 'Expense' account first.
        expense_root_account = frappe.db.get_value("Account", {"company": company_name, "root_type": "Expense", "is_group": 1})
        if not expense_root_account:
            frappe.throw(f"Could not find the root 'Expense' account for {company_name}.")

        # Step 1: Create the "Cost of Goods Sold" group account.
        cogs_account_name = f"Costos de los bienes vendidos - {company_abbr}"
        if not frappe.db.exists("Account", {"account_name": cogs_account_name, "company": company_name}):
            cogs_account = frappe.new_doc("Account")
            cogs_account.company = company_name
            cogs_account.account_name = "Costos de los bienes vendidos"
            cogs_account.parent_account = expense_root_account
            cogs_account.is_group = 1
            cogs_account.account_type = "Cost of Goods Sold"
            cogs_account.insert(ignore_permissions=True)
            frappe.db.commit() # Commit this parent before creating the child

        # Step 2: Create the "Stock Adjustment" child account.
        stock_adj_account_name = f"Stock Adjustment - {company_abbr}"
        if not frappe.db.exists("Account", {"account_name": stock_adj_account_name, "company": company_name}):
            stock_adj_account = frappe.new_doc("Account")
            stock_adj_account.company = company_name
            stock_adj_account.account_name = "Stock Adjustment"
            stock_adj_account.parent_account = cogs_account_name
            stock_adj_account.is_group = 0
            stock_adj_account.account_type = "Stock Adjustment"
            stock_adj_account.insert(ignore_permissions=True)

        # Step 3: Set the default on the Company document.
        frappe.db.set_value("Company", company_name, "stock_adjustment_account", stock_adj_account_name)

        frappe.db.commit()
        # --- THE CRITICAL FIX ENDS HERE ---

        return { "status": "success", "message": f"Successfully configured stock accounts for {company_name}." }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "setup_company_accounts_for_stock Error")
        frappe.throw(f"An error occurred during stock account setup: {str(e)}")

# --- CUSTOM CODE FOR CREDENTIAL GENERATION ---

@frappe.whitelist(allow_guest=False)
def generate_user_credentials(user_email):
    # The role name has the '\''s'\'' at the end.
    if "Credentials Manager" not in frappe.get_roles():
        frappe.throw(
            "Not permitted. You need the '\''Credentials Manager'\'' role to perform this action.",
            frappe.PermissionError
        )
    if frappe.session.user == user_email:
        frappe.throw("API user cannot reset their own credentials using this method.")
    if not frappe.db.exists("User", user_email):
        frappe.throw(f"User '\''{user_email}'\'' not found.")
    try:
        new_password = frappe.generate_hash(length=12)
        update_password(user=user_email, pwd=new_password)
        user_doc = frappe.get_doc("User", user_email)
        api_key = secrets.token_hex(16)
        api_secret = secrets.token_hex(16)

        # --- THE CRITICAL FIX ---
        # Set the keys directly on the document object.
        # The .save() method will handle the encryption automatically.
        user_doc.api_key = api_key
        user_doc.api_secret = api_secret
        # --- END OF FIX ---

        user_doc.save(ignore_permissions=True)
        frappe.db.commit()        
        return {
            "password": new_password,
            "api_key": api_key,
            "api_secret": api_secret
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Credential Generation Failed")
        frappe.throw(f"An error occurred while generating credentials: {str(e)}")


# API method to clear cache and restart all supervisor-managed processes


@frappe.whitelist(allow_guest=False)
def clear_cache_and_restart():
    user = frappe.get_user().name
    if user != "Administrator":
        frappe.throw("Only Administrator can perform this action", frappe.PermissionError)

    try:
        frappe.clear_cache()

        # Use bench restart instead of supervisorctl
        subprocess.check_call(["bench", "restart"])

        return {"status": "success", "message": "Cache cleared and backend restarted using bench."}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "clear_cache_and_restart")
        return {"status": "error", "message": str(e)}

# --- CUSTOM CODE FOR SALES ACCOUNT SETUP ---
@frappe.whitelist(allow_guest=False)
def setup_sales_accounts(company_name, company_abbr):
    # Security: Ensure only a privileged user can run this.
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            "Not permitted. You need the 'System Manager' role to perform this action.",
            frappe.PermissionError
        )

    # Input Validation
    if not company_name or not company_abbr:
        frappe.throw("Company Name and Abbreviation are required.")

    # Pre-flight Check: Ensure the company exists before we start.
    if not frappe.db.exists("Company", company_name):
        frappe.throw(f"Company '{company_name}' does not exist. Please create it first.")

    # --- YOUR WORKING CODE STARTS HERE ---
    try:
        # Part A: Discover the REAL names of the root accounts.
        asset_root_name = frappe.db.get_value("Account", {"company": company_name, "root_type": "Asset", "is_group": 1})
        income_root_name = frappe.db.get_value("Account", {"company": company_name, "root_type": "Income", "is_group": 1})

        # Convert your fatal error check to a proper API exception.
        if not all([asset_root_name, income_root_name]):
            frappe.throw("Could not discover the root Asset and Income accounts. Please check if the company's Chart of Accounts was created correctly.")

        # Define the names of the child accounts we will create.
        sales_account_final = f"Ventas - {company_abbr}"
        debtors_account_final = f"Deudores - {company_abbr}"

        # Part B: Create the "Sales" account under the discovered "Income" root.
        if not frappe.db.exists("Account", sales_account_final):
            sales_account = frappe.new_doc("Account")
            sales_account.account_name = "Ventas"
            sales_account.parent_account = income_root_name
            sales_account.company = company_name
            sales_account.account_type = "Income Account"
            sales_account.insert(ignore_permissions=True)

        # Part C: Create the "Debtors" (Receivable) account under the discovered "Assets" root.
        if not frappe.db.exists("Account", debtors_account_final):
            debtors_account = frappe.new_doc("Account")
            debtors_account.account_name = "Deudores"
            debtors_account.parent_account = asset_root_name
            debtors_account.company = company_name
            debtors_account.account_type = "Receivable"
            debtors_account.insert(ignore_permissions=True)

        # Part D: Update the Company doctype with these new defaults.
        frappe.db.set_value("Company", company_name, "default_income_account", sales_account_final)
        frappe.db.set_value("Company", company_name, "default_receivable_account", debtors_account_final)

        # Part E: Commit all changes to the database.
        frappe.db.commit()

        # --- YOUR CODE ENDS HERE ---

        # Return a clear, structured success message.
        return {
            "status": "success",
            "message": f"Sales and Debtors accounts configured successfully for company '{company_name}'.",
            "details": {
                "default_income_account": sales_account_final,
                "default_receivable_account": debtors_account_final
            }
        }

    except Exception as e:
        frappe.db.rollback() # Ensure atomicity: if any part fails, undo everything.
        frappe.log_error(frappe.get_traceback(), "Sales Account Setup Failed")
        frappe.throw(f"An error occurred during account setup: {str(e)}")

# --- CUSTOM CODE FOR COMPANY CREATION ---
@frappe.whitelist(allow_guest=False)
def create_custom_company(company_name, company_abbr):
    # Security: Only allow users with a powerful role like System Manager to create companies.
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            "Not permitted. You need the 'System Manager' role to perform this action.",
            frappe.PermissionError
        )

    # Input Validation
    if not company_name or not company_abbr:
        frappe.throw("Company Name and Abbreviation are required.")

    # Check if company already exists
    if frappe.db.exists("Company", company_name):
        return {"status": "skipped", "message": f"Company '{company_name}' already exists."}

    # --- YOUR WORKING CODE STARTS HERE ---
    try:
        # Part A: Create the Company with a Chart of Accounts Template.
        company_doc = frappe.new_doc("Company")
        company_doc.company_name = company_name
        company_doc.abbr = company_abbr
        company_doc.country = "Colombia"
        company_doc.default_currency = "COP"
        company_doc.chart_of_accounts = "Colombia PUC Simple"
        company_doc.insert(ignore_permissions=True)

        # Part B: Discover the Creditors group account.
        creditors_account = frappe.db.get_value("Account", {"company": company_name, "account_type": "Payable", "is_group": 1})

        # Part C: Create the custom "Stock Received But Not Billed" account.
        custom_account_name_base = "Activo recibido pero no facturado"
        custom_account_name_final = f"{custom_account_name_base} - {company_abbr}"
        if not frappe.db.exists("Account", custom_account_name_final):
            custom_account = frappe.new_doc("Account")
            custom_account.account_name = custom_account_name_base
            custom_account.parent_account = creditors_account
            custom_account.company = company_name
            custom_account.account_type = "Asset Received But Not Billed"
            custom_account.is_group = 0
            custom_account.insert(ignore_permissions=True)

        # Part D: Set the "Stock Received But Not Billed" default.
        frappe.db.set_value("Company", company_name, "stock_received_but_not_billed", custom_account_name_final)

        # Part E: Create and discover the Default Inventory Account.
        assets_account = frappe.db.get_value("Account", {"company": company_name, "root_type": "Asset", "is_group": 1})
        inventory_account_name_base = "Inventario de Mercancías"
        inventory_account_name_final = f"{inventory_account_name_base} - {company_abbr}"
        if not frappe.db.exists("Account", inventory_account_name_final):
            inventory_account = frappe.new_doc("Account")
            inventory_account.account_name = inventory_account_name_base
            inventory_account.parent_account = assets_account
            inventory_account.company = company_name
            inventory_account.account_type = "Stock"
            inventory_account.is_group = 0
            inventory_account.insert(ignore_permissions=True)

        # Part F: Set the Default Inventory Account on the Company record.
        frappe.db.set_value("Company", company_name, "default_inventory_account", inventory_account_name_final)

        # Part G: Commit all changes to the database.
        frappe.db.commit()

        # --- YOUR CODE ENDS HERE ---

        # Return a success confirmation
        return {"status": "success", "message": f"Company '{company_name}' with abbreviation '{company_abbr}' was created successfully."}

    except Exception as e:
        frappe.db.rollback()  # IMPORTANT: If anything fails, undo all changes.
        frappe.log_error(frappe.get_traceback(), "Custom Company Creation Failed")
        frappe.throw(f"An error occurred during company creation: {str(e)}")
