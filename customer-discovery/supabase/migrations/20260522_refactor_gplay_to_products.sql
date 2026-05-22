-- Drop dependent FK on voc_content first (references gplay_reviews which we're dropping)
ALTER TABLE public.voc_content
  DROP CONSTRAINT IF EXISTS voc_content_gplay_review_id_fkey;

-- Drop stale indexes from first migration (either naming variant)
DROP INDEX IF EXISTS public.idx_voc_content_gplay_review_id;
DROP INDEX IF EXISTS public.idx_voc_content_gplay_review;

-- Drop old tables (empty, safe)
DROP TABLE IF EXISTS public.gplay_reviews;
DROP TABLE IF EXISTS public.gplay_books;

-- Combined products table (covers books and apps)
CREATE TABLE public.gplay_products (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id           UUID        NOT NULL REFERENCES public.runs(id) ON DELETE CASCADE,
  product_type     TEXT        NOT NULL CHECK (product_type IN ('book', 'app')),
  discovery_phrase TEXT        NOT NULL,
  product_id       TEXT        NOT NULL,
  title            TEXT,
  authors          TEXT,
  description      TEXT,
  rating           NUMERIC,
  reviews_count    INTEGER,
  price            TEXT,
  thumbnail        TEXT,
  position         INTEGER,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Reviews table — FK now points to gplay_products
CREATE TABLE public.gplay_reviews (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  gplay_product_id UUID        NOT NULL REFERENCES public.gplay_products(id) ON DELETE CASCADE,
  run_id           UUID        NOT NULL REFERENCES public.runs(id) ON DELETE CASCADE,
  reviewer_name    TEXT,
  rating           INTEGER,
  snippet          TEXT,
  likes            INTEGER,
  review_date      TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Re-add the FK on voc_content pointing to the new gplay_reviews
ALTER TABLE public.voc_content
  ADD CONSTRAINT voc_content_gplay_review_id_fkey
  FOREIGN KEY (gplay_review_id) REFERENCES public.gplay_reviews(id) ON DELETE SET NULL;

-- Indexes
CREATE INDEX idx_gplay_products_run_id    ON public.gplay_products(run_id);
CREATE INDEX idx_gplay_products_type      ON public.gplay_products(product_type);
CREATE INDEX idx_gplay_reviews_product_id ON public.gplay_reviews(gplay_product_id);
CREATE INDEX idx_gplay_reviews_run_id     ON public.gplay_reviews(run_id);
CREATE INDEX idx_voc_content_gplay_review ON public.voc_content(gplay_review_id);

-- Grants
GRANT ALL ON public.gplay_products TO service_role;
GRANT ALL ON public.gplay_reviews  TO service_role;
