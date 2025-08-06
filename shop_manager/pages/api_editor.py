# shop_manager/shop_manager/pages/api_editor.py
import frappe
import os
from frappe.utils.file_manager import get_file_path
from frappe import _

def get_context(context):
    # Check if user has permission
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Not permitted. You need the 'System Manager' role."), frappe.PermissionError)
    
    # Get the path to the api.py file
    app_path = frappe.get_app_path('shop_manager')
    api_file_path = os.path.join(app_path, 'api.py')
    
    # Read the content of the api.py file
    try:
        with open(api_file_path, 'r') as file:
            context.api_code = file.read()
    except Exception as e:
        frappe.throw(_("Error reading API file: {0}").format(str(e)))
    
    return context
