create extension if not exists vector;

create table if not exists customers (
    id serial primary key,
    email text not null unique,
    first_name text not null,
    last_name text not null,
    city text not null,
    created_at timestamptz not null default now()
);

create table if not exists products (
    sku text primary key,
    name text not null,
    category text not null,
    price numeric(10, 2) not null
);

create table if not exists orders (
    id serial primary key,
    number text not null unique,
    customer_id int not null references customers (id),
    status text not null check (status in ('processing', 'shipped', 'delivered', 'cancelled')),
    placed_at timestamptz not null,
    total numeric(10, 2) not null
);

create index if not exists orders_customer_idx on orders (customer_id);

create table if not exists order_items (
    order_id int not null references orders (id) on delete cascade,
    sku text not null references products (sku),
    quantity int not null check (quantity > 0),
    unit_price numeric(10, 2) not null,
    primary key (order_id, sku)
);

create table if not exists shipments (
    order_id int primary key references orders (id) on delete cascade,
    carrier text not null,
    tracking_number text not null,
    status text not null check (status in ('label_created', 'in_transit', 'delayed', 'delivered')),
    shipped_at timestamptz,
    estimated_delivery date,
    delivered_at timestamptz
);

create table if not exists return_requests (
    id serial primary key,
    order_id int not null references orders (id),
    skus text[] not null,
    reason text not null,
    status text not null default 'requested',
    created_at timestamptz not null default now()
);

create table if not exists support_tickets (
    id serial primary key,
    customer_id int not null references customers (id),
    thread_id text,
    summary text not null,
    priority text not null check (priority in ('low', 'normal', 'high')),
    created_at timestamptz not null default now()
);

create table if not exists threads (
    id text primary key,
    customer_id int not null references customers (id),
    created_at timestamptz not null default now()
);

create table if not exists kb_documents (
    path text primary key,
    title text not null,
    content_hash text not null,
    ingested_at timestamptz not null default now()
);

-- vector(1536) matches text-embedding-3-small. Switching embedding models means
-- changing this and re-ingesting everything.
create table if not exists kb_chunks (
    id bigserial primary key,
    document_path text not null references kb_documents (path) on delete cascade,
    section text not null,
    content text not null,
    embedding vector(1536) not null,
    tsv tsvector generated always as (to_tsvector('english', content)) stored
);

create index if not exists kb_chunks_embedding_idx on kb_chunks using hnsw (embedding vector_cosine_ops);
create index if not exists kb_chunks_tsv_idx on kb_chunks using gin (tsv);
