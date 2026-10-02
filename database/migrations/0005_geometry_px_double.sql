-- US-04 RN06: coordenadas e raios em pixel da geometria passam de INTEGER
-- para DOUBLE PRECISION.
--
-- A 0001 gravava centro (maze_configs) e x/y/raio dos buracos (holes) como
-- INTEGER, arredondando ao pixel. Para o raio do buraco isso não é detalhe:
-- num vídeo em que o buraco tem ~8 px de raio, perder até 0,5 px é ~6% do
-- raio, e as zonas de proximidade (Épico D) e a região "buraco" do protocolo
-- de anotação (US-06) são definidas em múltiplos desse raio.
-- platform_radius_px e angle_deg já eram DOUBLE PRECISION desde a 0001.
--
-- INTEGER -> DOUBLE PRECISION é conversão sem perda; valores já gravados
-- continuam os mesmos (sem a fração que a 0001 descartou).

BEGIN;

ALTER TABLE maze_configs
    ALTER COLUMN center_x_px TYPE DOUBLE PRECISION,
    ALTER COLUMN center_y_px TYPE DOUBLE PRECISION;

ALTER TABLE holes
    ALTER COLUMN x_px TYPE DOUBLE PRECISION,
    ALTER COLUMN y_px TYPE DOUBLE PRECISION,
    ALTER COLUMN radius_px TYPE DOUBLE PRECISION;

COMMIT;
