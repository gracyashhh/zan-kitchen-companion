-- Zān database schema for Supabase (Postgres + Auth + private Storage)
-- Run once in Supabase Dashboard -> SQL Editor.

create extension if not exists pgcrypto;

-- -------------------- PROFILES --------------------
-- Passwords and emails remain in Supabase Auth. Never add password columns here.
create table if not exists public.profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    display_name text,
    gender text,
    height_cm numeric(5,1),
    weight_kg numeric(5,1),
    health_data_consent boolean not null default false,
    health_data_consent_at timestamptz,
    privacy_notice_version text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint profiles_height_range check (height_cm is null or height_cm between 50 and 260),
    constraint profiles_weight_range check (weight_kg is null or weight_kg between 10 and 500)
);

-- -------------------- PHOTO SCANS --------------------
-- Keeps the uploaded private image path, Muse request metadata, parsed API response,
-- and the corrected/confirmed values separately.
create table if not exists public.scans (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    scan_type text not null check (scan_type in ('fridge', 'meal')),
    image_path text,
    model_name text not null default 'muse-spark-1.3',
    prompt_version text,
    request_payload jsonb not null default '{}'::jsonb,
    response_payload jsonb not null default '{}'::jsonb,
    confirmed_payload jsonb,
    created_at timestamptz not null default now(),
    confirmed_at timestamptz
);
create index if not exists scans_user_created_idx on public.scans(user_id, created_at desc);

-- -------------------- FRIDGE INVENTORY --------------------
create table if not exists public.inventory_items (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    scan_id uuid references public.scans(id) on delete set null,
    name text not null,
    quantity text,
    expiry_date date,
    notes text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists inventory_user_active_idx on public.inventory_items(user_id, is_active, created_at desc);

-- -------------------- MEALS --------------------
create table if not exists public.meal_logs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    scan_id uuid references public.scans(id) on delete set null,
    meal_name text not null default 'Meal',
    total_calories integer,
    nutrition_source text,
    logged_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);
create index if not exists meals_user_logged_idx on public.meal_logs(user_id, logged_at desc);

create table if not exists public.meal_items (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    meal_id uuid not null references public.meal_logs(id) on delete cascade,
    name text not null,
    portion_grams numeric(8,2) not null check (portion_grams > 0),
    calories numeric(9,2),
    database_match text,
    sort_order integer not null default 0,
    created_at timestamptz not null default now()
);
create index if not exists meal_items_user_meal_idx on public.meal_items(user_id, meal_id, sort_order);

-- -------------------- RECIPE GENERATIONS --------------------
-- Each generation stores the exact ingredient snapshot and full structured model response.
-- input_hash lets Zān reuse an earlier result instead of paying for the same request again.
create table if not exists public.recipe_generations (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    model_name text not null default 'muse-spark-1.3',
    input_hash text,
    input_snapshot jsonb not null default '[]'::jsonb,
    request_payload jsonb not null default '{}'::jsonb,
    response_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists recipe_generations_user_created_idx on public.recipe_generations(user_id, created_at desc);
create index if not exists recipe_generations_user_hash_idx on public.recipe_generations(user_id, input_hash, created_at desc);

create table if not exists public.recipes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    generation_id uuid references public.recipe_generations(id) on delete cascade,
    name text not null,
    description text,
    prep_time text,
    cook_time text,
    servings text,
    recipe_data jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists recipes_user_created_idx on public.recipes(user_id, created_at desc);

-- -------------------- SHOPPING LIST --------------------
create table if not exists public.shopping_items (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    name text not null,
    quantity text,
    purchased boolean not null default false,
    source_recipe_id uuid references public.recipes(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists shopping_user_created_idx on public.shopping_items(user_id, created_at desc);

-- -------------------- ROW LEVEL SECURITY --------------------
-- Explicit grants + RLS: users can only access rows whose user_id is their Auth UID.
alter table public.profiles enable row level security;
alter table public.scans enable row level security;
alter table public.inventory_items enable row level security;
alter table public.meal_logs enable row level security;
alter table public.meal_items enable row level security;
alter table public.recipe_generations enable row level security;
alter table public.recipes enable row level security;
alter table public.shopping_items enable row level security;

revoke all on public.profiles, public.scans, public.inventory_items,
    public.meal_logs, public.meal_items, public.recipe_generations,
    public.recipes, public.shopping_items from anon, authenticated;

grant select, insert, update, delete on public.profiles, public.scans,
    public.inventory_items, public.meal_logs, public.meal_items,
    public.recipe_generations, public.recipes, public.shopping_items to authenticated;

-- Profiles
 drop policy if exists profiles_select_own on public.profiles;
 drop policy if exists profiles_insert_own on public.profiles;
 drop policy if exists profiles_update_own on public.profiles;
 drop policy if exists profiles_delete_own on public.profiles;
create policy profiles_select_own on public.profiles for select to authenticated using (user_id = (select auth.uid()));
create policy profiles_insert_own on public.profiles for insert to authenticated with check (user_id = (select auth.uid()));
create policy profiles_update_own on public.profiles for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy profiles_delete_own on public.profiles for delete to authenticated using (user_id = (select auth.uid()));

-- Scans
 drop policy if exists scans_select_own on public.scans;
 drop policy if exists scans_insert_own on public.scans;
 drop policy if exists scans_update_own on public.scans;
 drop policy if exists scans_delete_own on public.scans;
create policy scans_select_own on public.scans for select to authenticated using (user_id = (select auth.uid()));
create policy scans_insert_own on public.scans for insert to authenticated with check (user_id = (select auth.uid()));
create policy scans_update_own on public.scans for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy scans_delete_own on public.scans for delete to authenticated using (user_id = (select auth.uid()));

-- Inventory
 drop policy if exists inventory_select_own on public.inventory_items;
 drop policy if exists inventory_insert_own on public.inventory_items;
 drop policy if exists inventory_update_own on public.inventory_items;
 drop policy if exists inventory_delete_own on public.inventory_items;
create policy inventory_select_own on public.inventory_items for select to authenticated using (user_id = (select auth.uid()));
create policy inventory_insert_own on public.inventory_items for insert to authenticated with check (user_id = (select auth.uid()));
create policy inventory_update_own on public.inventory_items for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy inventory_delete_own on public.inventory_items for delete to authenticated using (user_id = (select auth.uid()));

-- Meals and meal components
 drop policy if exists meals_select_own on public.meal_logs;
 drop policy if exists meals_insert_own on public.meal_logs;
 drop policy if exists meals_update_own on public.meal_logs;
 drop policy if exists meals_delete_own on public.meal_logs;
create policy meals_select_own on public.meal_logs for select to authenticated using (user_id = (select auth.uid()));
create policy meals_insert_own on public.meal_logs for insert to authenticated with check (user_id = (select auth.uid()));
create policy meals_update_own on public.meal_logs for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy meals_delete_own on public.meal_logs for delete to authenticated using (user_id = (select auth.uid()));

 drop policy if exists meal_items_select_own on public.meal_items;
 drop policy if exists meal_items_insert_own on public.meal_items;
 drop policy if exists meal_items_update_own on public.meal_items;
 drop policy if exists meal_items_delete_own on public.meal_items;
create policy meal_items_select_own on public.meal_items for select to authenticated using (user_id = (select auth.uid()));
create policy meal_items_insert_own on public.meal_items for insert to authenticated with check (user_id = (select auth.uid()));
create policy meal_items_update_own on public.meal_items for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy meal_items_delete_own on public.meal_items for delete to authenticated using (user_id = (select auth.uid()));

-- Recipe generations and saved recipes
 drop policy if exists recipe_generations_select_own on public.recipe_generations;
 drop policy if exists recipe_generations_insert_own on public.recipe_generations;
 drop policy if exists recipe_generations_update_own on public.recipe_generations;
 drop policy if exists recipe_generations_delete_own on public.recipe_generations;
create policy recipe_generations_select_own on public.recipe_generations for select to authenticated using (user_id = (select auth.uid()));
create policy recipe_generations_insert_own on public.recipe_generations for insert to authenticated with check (user_id = (select auth.uid()));
create policy recipe_generations_update_own on public.recipe_generations for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy recipe_generations_delete_own on public.recipe_generations for delete to authenticated using (user_id = (select auth.uid()));

 drop policy if exists recipes_select_own on public.recipes;
 drop policy if exists recipes_insert_own on public.recipes;
 drop policy if exists recipes_update_own on public.recipes;
 drop policy if exists recipes_delete_own on public.recipes;
create policy recipes_select_own on public.recipes for select to authenticated using (user_id = (select auth.uid()));
create policy recipes_insert_own on public.recipes for insert to authenticated with check (user_id = (select auth.uid()));
create policy recipes_update_own on public.recipes for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy recipes_delete_own on public.recipes for delete to authenticated using (user_id = (select auth.uid()));

-- Shopping list
 drop policy if exists shopping_select_own on public.shopping_items;
 drop policy if exists shopping_insert_own on public.shopping_items;
 drop policy if exists shopping_update_own on public.shopping_items;
 drop policy if exists shopping_delete_own on public.shopping_items;
create policy shopping_select_own on public.shopping_items for select to authenticated using (user_id = (select auth.uid()));
create policy shopping_insert_own on public.shopping_items for insert to authenticated with check (user_id = (select auth.uid()));
create policy shopping_update_own on public.shopping_items for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy shopping_delete_own on public.shopping_items for delete to authenticated using (user_id = (select auth.uid()));

-- -------------------- PRIVATE PHOTO BUCKET --------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'zan-private-images',
    'zan-private-images',
    false,
    10485760,
    array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update set
    public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists zan_images_select_own on storage.objects;
drop policy if exists zan_images_insert_own on storage.objects;
drop policy if exists zan_images_update_own on storage.objects;
drop policy if exists zan_images_delete_own on storage.objects;
create policy zan_images_select_own on storage.objects for select to authenticated
using (bucket_id = 'zan-private-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy zan_images_insert_own on storage.objects for insert to authenticated
with check (bucket_id = 'zan-private-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy zan_images_update_own on storage.objects for update to authenticated
using (bucket_id = 'zan-private-images' and (storage.foldername(name))[1] = (select auth.uid())::text)
with check (bucket_id = 'zan-private-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy zan_images_delete_own on storage.objects for delete to authenticated
using (bucket_id = 'zan-private-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
