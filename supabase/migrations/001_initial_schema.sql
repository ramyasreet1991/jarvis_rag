-- Nifty200 Momentum 30 Agentic Trading Database Schema

-- Enable RLS
alter table if exists public.stocks enable row level security;
alter table if exists public.analysis_results enable row level security;
alter table if exists public.red_team_flags enable row level security;

-- Stocks table (Nifty200 Momentum 30 constituents)
create table if not exists public.stocks (
    id uuid default gen_random_uuid() primary key,
    symbol text not null unique,
    name text,
    sector text,
    is_active boolean default true,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- Analysis results (full pipeline output)
create table if not exists public.analysis_results (
    id uuid default gen_random_uuid() primary key,
    symbol text not null references public.stocks(symbol),
    signal text not null check (signal in ('STRONG_BUY', 'BUY', 'WEAK_BUY', 'HOLD', 'WEAK_SELL', 'SELL', 'STRONG_SELL', 'AVOID')),
    composite_score integer not null,
    confidence integer not null,
    position_size_pct numeric(5,2),
    entry_price numeric(12,2),
    stop_loss numeric(12,2),
    target_price numeric(12,2),
    rationale text,
    red_team_status text,
    red_team_score integer,
    red_team_flags jsonb,
    fundamental_verdict text,
    fundamental_score integer,
    roe numeric(8,2),
    debt_equity numeric(8,2),
    peg_ratio numeric(8,2),
    technical_signal text,
    technical_score integer,
    momentum_6m numeric(8,2),
    momentum_12m numeric(8,2),
    rsi_14 numeric(5,2),
    ema_trend text,
    news_score integer,
    news_sentiment numeric(5,2),
    news_recommendation text,
    news_headlines jsonb,
    created_at timestamp with time zone default now(),
    analysis_date date default current_date
);

-- Red Team flags history
create table if not exists public.red_team_flags (
    id uuid default gen_random_uuid() primary key,
    symbol text not null references public.stocks(symbol),
    flag_type text not null,
    flag_description text,
    severity text check (severity in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    source_url text,
    detected_at timestamp with time zone default now(),
    resolved_at timestamp with time zone,
    is_active boolean default true
);

-- News sentiment cache
create table if not exists public.news_sentiment (
    id uuid default gen_random_uuid() primary key,
    symbol text not null references public.stocks(symbol),
    headline text,
    source text,
    sentiment_score numeric(5,2),
    urgency_score numeric(5,2),
    published_at timestamp with time zone,
    fetched_at timestamp with time zone default now()
);

-- Create indexes
create index if not exists idx_analysis_results_symbol on public.analysis_results(symbol);
create index if not exists idx_analysis_results_date on public.analysis_results(analysis_date);
create index if not exists idx_analysis_results_signal on public.analysis_results(signal);
create index if not exists idx_red_team_flags_symbol on public.red_team_flags(symbol);
create index if not exists idx_news_sentiment_symbol on public.news_sentiment(symbol);

-- RLS Policies
alter table public.stocks enable row level security;
create policy "Allow public read" on public.stocks for select using (true);

alter table public.analysis_results enable row level security;
create policy "Allow public read" on public.analysis_results for select using (true);

alter table public.red_team_flags enable row level security;
create policy "Allow public read" on public.red_team_flags for select using (true);

alter table public.news_sentiment enable row level security;
create policy "Allow public read" on public.news_sentiment for select using (true);

-- Function to get latest analysis for each stock
create or replace function public.get_latest_analysis()
returns table (
    symbol text,
    signal text,
    composite_score integer,
    confidence integer,
    created_at timestamp with time zone
) as $$
begin
    return query
    select distinct on (ar.symbol)
        ar.symbol,
        ar.signal,
        ar.composite_score,
        ar.confidence,
        ar.created_at
    from public.analysis_results ar
    order by ar.symbol, ar.created_at desc;
end;
$$ language plpgsql;

-- Function to get top picks
create or replace function public.get_top_picks(limit_count integer default 5)
returns table (
    symbol text,
    signal text,
    composite_score integer,
    confidence integer,
    rationale text
) as $$
begin
    return query
    select 
        ar.symbol,
        ar.signal,
        ar.composite_score,
        ar.confidence,
        ar.rationale
    from public.analysis_results ar
    where ar.signal in ('STRONG_BUY', 'BUY')
    and ar.created_at >= now() - interval '24 hours'
    order by ar.composite_score desc
    limit limit_count;
end;
$$ language plpgsql;

-- Function to get avoid list
create or replace function public.get_avoid_list()
returns table (
    symbol text,
    signal text,
    red_team_status text,
    red_team_flags jsonb,
    rationale text
) as $$
begin
    return query
    select 
        ar.symbol,
        ar.signal,
        ar.red_team_status,
        ar.red_team_flags,
        ar.rationale
    from public.analysis_results ar
    where ar.signal = 'AVOID'
    and ar.created_at >= now() - interval '24 hours'
    order by ar.red_team_score asc;
end;
$$ language plpgsql;
