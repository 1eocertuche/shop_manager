# Shop Manager

Shop Manager is a Frappe app that provides API endpoints for managing various aspects of your ERPNext instance, including company setup, account configuration, and user credential management. It also includes an API Editor that allows you to edit the API code directly from the ERPNext interface.

## Features

- Company creation with default accounts
- Account setup for sales, stock, and cash transactions
- User credential generation
- API Editor for modifying API endpoints directly from the UI
- Automatic application of API changes

## Installation

1. Go to the Frappe Cloud Marketplace
2. Search for "Shop Manager"
3. Click Install

## Usage

### Using the API Endpoints

The app provides several API endpoints that can be used to automate various tasks. These endpoints are documented in the `api.py` file.

### Using the API Editor

1. Navigate to `/api-editor` in your ERPNext site
2. Edit the API code as needed
3. Click "Save Changes"
4. The system will automatically apply the changes

## Requirements

- ERPNext v15
- System Manager role to use the API Editor

## License

MIT

### aiTender

create invoices via API

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app shop_manager
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/shop_manager
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
