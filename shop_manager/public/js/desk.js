// shop_manager/public/js/desk.js
frappe.ready(function() {
    if (frappe.boot.user.roles.includes('System Manager')) {
        // Add API Editor to the menu
        frappe.breadcrumbs.add('Shop Manager', 'API Editor');
        
        // Add a menu item
        frappe.router.on('change', function() {
            if (frappe.route[0] === 'api-editor') {
                frappe.breadcrumbs.add('Shop Manager', 'API Editor');
            }
        });
    }
});
