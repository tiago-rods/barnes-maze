-- US-05: rotação da plataforma em cada trial.
--
-- Em graus, normalizada para 0 <= x < 360 (mesma faixa de holes.angle_deg),
-- positiva no sentido horário na tela (mesma convenção angular de
-- src/barnes/geometry/holes.py).
--
-- Sem DEFAULT de propósito (US-05 RN01): NULL significa "rotação não
-- registrada", e a análise longitudinal recusa o trial (Cenário 3) em vez de
-- assumir 0° em silêncio. Trials carregados antes desta migração ficam NULL.
-- Com B4 = "LNBio não rotaciona" (RN04), quem grava o trial informa 0
-- explicitamente — a coluna e o caminho de código permanecem.

BEGIN;

ALTER TABLE trials
    ADD COLUMN rotation_deg DOUBLE PRECISION
        CHECK (rotation_deg >= 0 AND rotation_deg < 360);

COMMIT;
