BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE app_role AS ENUM ('super_admin', 'wisp_admin');
CREATE TYPE subscriber_status AS ENUM ('active', 'suspended', 'disabled');
CREATE TYPE address_kind AS ENUM ('private', 'public');

CREATE TABLE app_settings (
    key text PRIMARY KEY,
    value jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admin_users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role app_role NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sites (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    description text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE nas_routers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id bigint REFERENCES sites(id) ON DELETE RESTRICT,
    name text NOT NULL UNIQUE,
    loopback_ip inet NOT NULL UNIQUE,
    radius_secret_ciphertext text NOT NULL,
    api_port integer NOT NULL DEFAULT 8728 CHECK (api_port BETWEEN 1 AND 65535),
    coa_port integer NOT NULL DEFAULT 3799 CHECK (coa_port BETWEEN 1 AND 65535),
    enabled boolean NOT NULL DEFAULT true,
    last_seen_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE service_packages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    advertised_down_mbps numeric(10,2) NOT NULL CHECK (advertised_down_mbps > 0),
    advertised_up_mbps numeric(10,2) NOT NULL CHECK (advertised_up_mbps > 0),
    provisioned_down_mbps numeric(10,2) NOT NULL CHECK (provisioned_down_mbps > 0),
    provisioned_up_mbps numeric(10,2) NOT NULL CHECK (provisioned_up_mbps > 0),
    is_legacy boolean NOT NULL DEFAULT false,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ip_pools (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    kind address_kind NOT NULL,
    start_address inet NOT NULL,
    end_address inet NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE uisp_customers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uisp_client_id text NOT NULL UNIQUE,
    display_name text NOT NULL,
    account_status text NOT NULL DEFAULT 'unknown',
    billing_email text,
    billing_phone text,
    billing_address jsonb,
    raw_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_synced_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE subscribers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL UNIQUE,
    password_ciphertext text NOT NULL,
    display_name text NOT NULL,
    status subscriber_status NOT NULL DEFAULT 'active',
    package_id bigint NOT NULL REFERENCES service_packages(id) ON DELETE RESTRICT,
    ip_pool_id bigint REFERENCES ip_pools(id) ON DELETE RESTRICT,
    framed_ip_address inet NOT NULL UNIQUE,
    site_id bigint REFERENCES sites(id) ON DELETE RESTRICT,
    uisp_customer_id bigint REFERENCES uisp_customers(id) ON DELETE SET NULL,
    uisp_link_confirmed_at timestamptz,
    legacy_attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE radius_sessions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acct_session_id text NOT NULL,
    subscriber_id bigint REFERENCES subscribers(id) ON DELETE SET NULL,
    router_id bigint REFERENCES nas_routers(id) ON DELETE SET NULL,
    username text NOT NULL,
    framed_ip_address inet,
    started_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    stopped_at timestamptz,
    input_octets bigint NOT NULL DEFAULT 0,
    output_octets bigint NOT NULL DEFAULT 0,
    terminate_cause text,
    UNIQUE (acct_session_id, router_id)
);

CREATE INDEX radius_sessions_online_idx ON radius_sessions (username) WHERE stopped_at IS NULL;
CREATE INDEX radius_sessions_started_idx ON radius_sessions (started_at DESC);
CREATE INDEX subscribers_uisp_idx ON subscribers (uisp_customer_id);

CREATE TABLE speed_tests (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subscriber_id bigint NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
    router_id bigint REFERENCES nas_routers(id) ON DELETE SET NULL,
    tested_at timestamptz NOT NULL DEFAULT now(),
    download_mbps numeric(10,2) NOT NULL,
    upload_mbps numeric(10,2) NOT NULL,
    latency_ms numeric(10,2),
    jitter_ms numeric(10,2),
    packet_loss_percent numeric(5,2),
    client_ip inet,
    user_agent text
);

CREATE TABLE audit_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_type text NOT NULL,
    actor_id bigint,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text,
    before_value jsonb,
    after_value jsonb,
    source_ip inet,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO service_packages
    (name, advertised_down_mbps, advertised_up_mbps, provisioned_down_mbps, provisioned_up_mbps)
VALUES
    ('5/5 Mbps', 5, 5, 6, 6),
    ('10/10 Mbps', 10, 10, 11, 11),
    ('20/20 Mbps', 20, 20, 21, 21);

INSERT INTO app_settings (key, value) VALUES
    ('product', '{"name":"Net2Net Local RADIUS Manager","powered_by_locked":true}'),
    ('suspension', '{"rate_limit":"8k/8k","uisp_sync_minutes":5}'),
    ('retention', '{"accounting_months":24,"backup_daily_count":7,"pre_upgrade_count":1}');

COMMIT;

