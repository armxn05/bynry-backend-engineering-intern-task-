# Example corrected Flask endpoint
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError
from models import db, Product, Inventory, Warehouse  # assumed imports

bp = Blueprint('api', __name__)

@bp.route('/api/products', methods=['POST'])
def create_product():
    data = request.get_json() or {}
    name = data.get('name')
    sku = data.get('sku')
    price_raw = data.get('price')          # optional
    warehouse_id = data.get('warehouse_id')# optional
    initial_qty = data.get('initial_quantity')

    # Basic validation
    if not name or not sku:
        return jsonify({"error": "name and sku fields are required"}), 400

    # Parse price using Decimal to avoid floating point issues
    price = None
    if price_raw is not None:
        try:
            price = Decimal(str(price_raw))
            if price < 0:
                return jsonify({"error": "price must be non-negative"}), 400
        except (InvalidOperation, ValueError):
            return jsonify({"error": "invalid price format"}), 400

    # If warehouse_id provided, validate existence (and ownership if multi-tenant)
    if warehouse_id is not None:
        warehouse = Warehouse.query.get(warehouse_id)
        if not warehouse:
            return jsonify({"error": "warehouse_id not found"}), 404
        # Optional: check warehouse.company_id matches current user's company

    # Use a single DB transaction for product + inventory (atomic)
    try:
        with db.session.begin():  # commits on success, rolls back on exception
            product = Product(name=name, sku=sku, price=price)
            db.session.add(product)
            db.session.flush()  # ensures product.id is available

            # Only create/update inventory if both warehouse and initial_qty provided and positive
            if warehouse_id is not None and initial_qty is not None:
                try:
                    qty = int(initial_qty)
                    if qty < 0:
                        raise ValueError()
                except ValueError:
                    raise ValueError("initial_quantity must be a non-negative integer")

                if qty > 0:
                    # Upsert inventory for (product, warehouse) to avoid duplicates
                    inv = (Inventory.query
                           .filter_by(product_id=product.id, warehouse_id=warehouse_id)
                           .with_for_update(nowait=False)
                           .first())
                    if inv:
                        inv.quantity = inv.quantity + qty
                    else:
                        inv = Inventory(product_id=product.id,
                                        warehouse_id=warehouse_id,
                                        quantity=qty)
                        db.session.add(inv)

        # Success
        return jsonify({"message": "Product created", "product_id": product.id}), 201

    except IntegrityError as e:
        db.session.rollback()
        # Detect unique SKU violation (DB-level constraint required)
        msg = str(e).lower()
        if 'unique' in msg or 'duplicate' in msg or 'already exists' in msg:
            return jsonify({"error": "SKU already exists"}), 409
        return jsonify({"error": "database integrity error", "details": str(e)}), 500

    except ValueError as ve:
        db.session.rollback()
        return jsonify({"error": str(ve)}), 400

    except Exception as ex:
        db.session.rollback()
        # logging.exception/ex audit would go here
        return jsonify({"error": "internal server error", "details": str(ex)}), 500
