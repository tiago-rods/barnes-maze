-- US-02 RN04: `scale verify` recusa reusar um dos dois segmentos da
-- calibração como a terceira distância independente. Isso exige saber as
-- coordenadas desses dois segmentos numa chamada posterior (processo
-- separado de `scale calibrate`) — por isso ficam guardados aqui, e não só
-- o fator calculado (px_per_10cm, já coberto pela 0002).

BEGIN;

-- TEXT, não JSONB: o psycopg (de)serializa json/jsonb automaticamente em
-- alguns contextos, o que entraria em conflito com o json.dumps/json.loads
-- explícito em barnes.db.calibration. Mantém o controle só na aplicação,
-- mesma escolha já usada pela PR original para este mesmo dado.
ALTER TABLE maze_configs
    ADD COLUMN calibration_segments TEXT;

COMMIT;
