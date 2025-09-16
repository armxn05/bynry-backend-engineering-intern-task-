-- companies
CREATE TABLE companies (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- warehouses
CREATE TABLE warehouses (
  id BIGSERIAL PRIMARY KEY,
  company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  address TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_warehouses_company ON warehouses(company_id);

-- products (global catalog, SKU unique platform-wide)
CREATE TABLE products (
  id BIGSERIAL PRIMARY KEY,
  sku VARCHAR(128) NOT NULL UNIQUE, -- platform-wide unique
  name TEXT NOT NULL,
  description TEXT,
  product_type VARCHAR(64), -- e.g. "consumable", "electronics", "bundle"
  price NUMERIC(14,4), -- use decimal for money
  is_bundle BOOLEAN DEFAULT FALSE,
  low_stock_threshold INT DEFAULT NULL, -- product-level threshold (can be null)
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_products_sku ON products(sku);

-- bundle_items (for bundle products)
CREATE TABLE bundle_items (
  bundle_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  component_product_id BIGINT NOT NULL REFERENCES products(id),
  qty INT NOT NULL DEFAULT 1,
  PRIMARY KEY (bundle_id, component_product_id)
);
-- only use when products.is_bundle = true

-- inventories (one row per product x warehouse)
CREATE TABLE inventories (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  warehouse_id BIGINT NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
  quantity INT NOT NULL DEFAULT 0,
  reserved INT NOT NULL DEFAULT 0, -- optional if we support reservations
  last_updated TIMESTAMPTZ DEFAULT now(),
  UNIQUE (product_id, warehouse_id)
);
CREATE INDEX idx_inventory_product ON inventories(product_id);
CREATE INDEX idx_inventory_warehouse ON inventories(warehouse_id);

-- inventory_movements (audit trail)
CREATE TABLE inventory_movements (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES products(id),
  warehouse_id BIGINT NOT NULL REFERENCES warehouses(id),
  delta INT NOT NULL, -- positive for inbound, negative for outbound
  reason VARCHAR(64) NOT NULL, -- e.g., 'purchase', 'sale', 'adjustment', 'transfer'
  reference_id BIGINT, -- e.g., order id, purchase id
  created_by BIGINT, -- user id (optional)
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_movements_product_warehouse ON inventory_movements(product_id, warehouse_id, created_at);

-- suppliers
CREATE TABLE suppliers (
  id BIGSERIAL PRIMARY KEY,
  company_id BIGINT NOT NULL REFERENCES companies(id), -- supplier relationship for this company
  name TEXT NOT NULL,
  contact_email TEXT,
  contact_phone TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- supplier_products (supplier's catalog / price / lead time)
CREATE TABLE supplier_products (
  supplier_id BIGINT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
  product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  supplier_sku VARCHAR(128),
  cost_price NUMERIC(14,4),
  lead_time_days INT, -- expected shipping lead time
  preferred BOOLEAN DEFAULT FALSE,
  PRIMARY KEY (supplier_id, product_id)
);
CREATE INDEX idx_supplier_products_product ON supplier_products(product_id);

-- sales_orders + order_items (to track sales activity)
CREATE TABLE sales_orders (
  id BIGSERIAL PRIMARY KEY,
  company_id BIGINT NOT NULL REFERENCES companies(id),
  warehouse_id BIGINT NOT NULL REFERENCES warehouses(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  status VARCHAR(32) -- 'completed', 'cancelled', ...
);

CREATE TABLE order_items (
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES sales_orders(id) ON DELETE CASCADE,
  product_id BIGINT NOT NULL REFERENCES products(id),
  quantity INT NOT NULL,
  unit_price NUMERIC(14,4)
);
CREATE INDEX idx_order_items_product ON order_items(product_id);

-- (Optional) product_locations for more granular info like bins:
CREATE TABLE product_locations (
  id BIGSERIAL PRIMARY KEY,
  inventory_id BIGINT NOT NULL REFERENCES inventories(id),
  bin_code VARCHAR(64)
);
