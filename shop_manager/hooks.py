app_name = "shop_manager"
app_title = "create invoices via API"
app_publisher = "ayte.co"
app_description = "endpoints to create companies, accounts and invoices in erp next"
app_email = "leo@ayte.co"
app_license = "MIT"
# Add to hooks.py
# ... existing hooks ...

# Website Routes
website_route_rules = [
    {"from_route": "/api-editor", "to_route": "api_editor"}
]
# Include CodeMirror for better code editing
app_include_js = [
    "/assets/shop_manager/js/codemirror.js",
    "/assets/shop_manager/js/mode/python/python.js",
    "/assets/shop_manager/js/addon/edit/closebrackets.js",
    "/assets/shop_manager/js/addon/edit/matchbrackets.js"
]

app_include_css = "/assets/shop_manager/css/codemirror.css"
