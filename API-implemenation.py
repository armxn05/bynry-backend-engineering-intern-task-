# alerts.py (Flask blueprint)
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from models import db, Company, Warehouse, Product, Inventory, OrderItem, SalesOrder, Supplier, SupplierProduct

alerts_bp = Blueprint('alerts', __name__)

@alerts_bp.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def low_stock_alerts(company_id):
    # Configurable params
    DAYS_WINDOW = int(request.args.get('days_window', 90))  # recent-sales window
    min_days_window = 7
    if DAYS_WINDOW < min_days_window:
        DAYS_WINDOW = min_days_window

    now = datetime.utcnow()
    cutoff = now - timedelta(days=DAYS_WINDOW)

    # Default thresholds by product_type (fallback)
    DEFAULT_THRESHOLD_BY_TYPE = {
        'consumable': 10,
        'electronics': 5,
        'bundle': 20,
        'default': 10
    }

    # 1) get all warehouses for company
    warehouse_ids_q = db.session.query(Warehouse.id).filter(Warehouse.company_id == company_id).subquery()

    # 2) aggregate sales for (product_id, warehouse_id) in the window
    sales_agg = (
        db.session.query(
            OrderItem.product_id.label('product_id'),
            SalesOrder.warehouse_id.label('warehouse_id'),
            func.sum(OrderItem.quantity).label('total_sold')
        )
        .join(SalesOrder, SalesOrder.id == OrderItem.order_id)
        .filter(
            SalesOrder.warehouse_id.in_(warehouse_ids_q),
            SalesOrder.company_id == company_id,
            SalesOrder.status == 'completed',  # only completed sales count
            SalesOrder.created_at >= cutoff
        )
        .group_by(OrderItem.product_id, SalesOrder.warehouse_id)
        .subquery()
    )

    # 3) find inventories under threshold AND with recent sales (join to sales_agg)
    q = (
        db.session.query(
            Inventory.id.label('inventory_id'),
            Inventory.product_id,
            Product.name.label('product_name'),
            Product.sku.label('sku'),
            Inventory.warehouse_id,
            Warehouse.name.label('warehouse_name'),
            Inventory.quantity.label('current_stock'),
            Product.low_stock_threshold.label('product_threshold'),
            Product.product_type.label('product_type'),
            sales_agg.c.total_sold.label('total_sold')
        )
        .join(Product, Product.id == Inventory.product_id)
        .join(Warehouse, Warehouse.id == Inventory.warehouse_id)
        .join(sales_agg, and_(
            sales_agg.c.product_id == Inventory.product_id,
            sales_agg.c.warehouse_id == Inventory.warehouse_id
        ))
        .filter(Warehouse.company_id == company_id)
    )

    results = q.all()

    alerts = []
    product_ids = set()
    for row in results:
        product_ids.add(row.product_id)

        # determine threshold: product-level else type default
        threshold = row.product_threshold
        if threshold is None:
            threshold = DEFAULT_THRESHOLD_BY_TYPE.get(row.product_type, DEFAULT_THRESHOLD_BY_TYPE['default'])

        # skip if not actually below threshold (defensive check)
        if row.current_stock >= threshold:
            continue

        # avg daily sales
        avg_daily_sales = float(row.total_sold) / float(DAYS_WINDOW) if row.total_sold and row.total_sold > 0 else 0.0
        if avg_daily_sales <= 0:
            # Per business rule: only alert products with recent sales activity
            # We joined to sales_agg so total_sold > 0, but we keep defensive check
            continue

        # compute days until stockout (ceil)
        import math
        days_until_stockout = math.ceil(float(row.current_stock) / avg_daily_sales) if avg_daily_sales > 0 else None

        alerts.append({
            "product_id": row.product_id,
            "product_name": row.product_name,
            "sku": row.sku,
            "warehouse_id": row.warehouse_id,
            "warehouse_name": row.warehouse_name,
            "current_stock": int(row.current_stock),
            "threshold": int(threshold),
            "days_until_stockout": int(days_until_stockout) if days_until_stockout is not None else None,
            # supplier will be filled in below (lazy load to keep primary query simple)
            "supplier": None
        })

    # 4) attach supplier info per product (pick preferred or lowest lead time)
    if alerts:
        product_list = [a["product_id"] for a in alerts]
        # fetch supplier_products for these products
        supplier_rows = (
            db.session.query(
                SupplierProduct.product_id,
                Supplier.id.label('supplier_id'),
                Supplier.name.label('supplier_name'),
                Supplier.contact_email.label('contact_email'),
                SupplierProduct.preferred,
                SupplierProduct.lead_time_days
            )
            .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
            .filter(SupplierProduct.product_id.in_(product_list))
            .all()
        )

        # group by product_id and choose best supplier
        from collections import defaultdict
        sp_map = defaultdict(list)
        for s in supplier_rows:
            sp_map[s.product_id].append(s)

        # choose supplier per product
        supplier_choice = {}
        for pid, srows in sp_map.items():
            # prefer preferred suppliers; else smallest lead_time
            preferred = [s for s in srows if s.preferred]
            if preferred:
                chosen = sorted(preferred, key=lambda x: (x.lead_time_days if x.lead_time_days is not None else 9999))[0]
            else:
                chosen = sorted(srows, key=lambda x: (x.lead_time_days if x.lead_time_days is not None else 9999))[0]
            supplier_choice[pid] = {
                "id": int(chosen.supplier_id),
                "name": chosen.supplier_name,
                "contact_email": chosen.contact_email
            }

        # map back into alerts
        for a in alerts:
            if a["product_id"] in supplier_choice:
                a["supplier"] = supplier_choice[a["product_id"]]
            else:
                a["supplier"] = None

    return jsonify({"alerts": alerts, "total_alerts": len(alerts)}), 200
