-- Executado uma única vez pelo entrypoint da imagem postgres, quando o volume
-- é criado. Cria o banco isolado da suíte de testes; o schema de ambos os
-- bancos vem de `barnes db migrate`, não daqui.
CREATE DATABASE barnes_test OWNER barnes;
