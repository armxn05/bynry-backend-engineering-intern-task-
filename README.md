(for correct-implementation.py file) 

Assumptions used in this function : 

-Product, Inventory, Warehouse are SQLAlchemy models.

-Product.sku has a UNIQUE constraint at DB level.

-db is SQLAlchemy session from flask_sqlalchemy.

-initial_quantity and warehouse_id are optional. We only create inventory if both provided and 
initial_quantity > 0.

-Price is optional; if present it must be decimal-friendly.

Notes / explanation of fixes

-Single transaction (with db.session.begin()): ensures product + inventory succeed or fail together.

-SKU uniqueness handling: assumes DB-level unique constraint and traps IntegrityError to return 409 Conflict.

-Money stored as Decimal: parse prices with Decimal(str(...)) to avoid float imprecision.

-Inventory upsert: checks existing Inventory row and updates quantity instead of creating duplicates.

-Field validation & HTTP codes: returns meaningful status codes (400, 404, 409, 201).

-Warehouse check: avoids assigning inventory to invalid warehouses.

-Concurrency locking hint: .with_for_update() used to prevent race conditions while updating inventory.






(for database-design.sql file )

Requirements (given)
-Companies can have multiple warehouses.

-Products can be stored in multiple warehouses with different quantities.

-Track when inventory levels change.

-Suppliers provide products to companies.

-Some products might be "bundles" containing other products.

My additional design assumptions
-This is a multi-tenant app: companies owns warehouses and suppliers are linked to company.

-SKU uniqueness: SKUs must be unique across the whole platform (global uniqueness).

-We need sales/transactions to determine "recent sales activity".

-Monetary values use NUMERIC/DECIMAL.

-We want an audit trail for inventory changes.

Questions / Gaps to ask the product team : 

1. Threshold rule granularity
Is low_stock_threshold per product, per product+warehouse, or per product type? Should warehouses override product-level thresholds?

2. Definition of "recent sales activity"
How many days should "recent" cover (30/60/90)? Does this include pending orders?

3. Units & conversions
Are there units of measure and conversions (kg, piece, box)? Are BOMs needed?

4. Multi-tenancy / ownership
Can multiple companies share the same product entry (same SKU)? Or is every product created by a company? (We assumed SKU global.)

5. Reservations & backorders
Should reserved stock / fulfilling orders reduce available stock? How to treat allocated vs available?

6. Transfers between warehouses
Should we model transfers as inventory_movements(reason='transfer')? Any special rules?

7. Supplier selection rules
How to pick supplier for reordering (cheapest vs preferred vs shortest lead time)?

8. Perishable / lot / serial tracking
Do we need batch/lot/expiry tracking or serialized inventory?

9. Currency & pricing
Multi-currency support? Pricing per company or global?

10. Performance SLAs
Expected scale (#products, #warehouses, read/writes per minute)? This affects indexing and partitioning choices.

Indexes & constraints summary

-products.sku UNIQUE and indexed.

-inventories(product_id, warehouse_id) unique + index for fast joins.

-inventory_movements(product_id, warehouse_id, created_at) index for range queries.

-supplier_products(product_id) index to find suppliers quickly.

-Referential integrity with ON DELETE CASCADE as appropriate.