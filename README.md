# Projeto Computação Pervasiva e Ubíqua

## Wearable Tutor

Inicialização do ESP32

* Montagem padrão seguindo a aula 3 (Sensores) com LEDs.

* Código principal para o ESP32: main.py, que deve ser rodado no interpretador .venv criado, contendo todas as dependências.

* Quando o ESP32 estiver pronto para funcionar, rodar o main.py uma única vez para descobrir o IP do ESP32, e, assim que ele for descoberto, parar de rodar o código. Após isso, salvar o código dentro do ESP32 para rodar automaticamente.

---

## Sobre o projeto

O **Wearable Tutor** é um projeto desenvolvido para a disciplina de Computação Pervasiva e Ubíqua.

A proposta do sistema é usar um dispositivo vestível, como um smartwatch, para identificar se o usuário está próximo da mesa de estudo. A partir dessa presença, o sistema controla uma sessão de estudos e envia alertas visuais para um ESP32 com LEDs.

Além disso, o projeto registra os dados das sessões em um banco local e exibe essas informações em um dashboard simples.

## Funcionamento geral

O sistema funciona da seguinte forma:

1. O Python procura dispositivos Bluetooth próximos.
2. Quando encontra o smartwatch configurado, verifica a força do sinal.
3. Se o usuário estiver próximo, uma sessão de estudos é iniciada.
4. Durante a sessão, o tempo de estudo é contabilizado.
5. Caso o usuário se afaste, o sistema pausa ou encerra a sessão.
6. O ESP32 recebe alertas por HTTP para acionar os LEDs.
7. Os dados são salvos em um banco SQLite.
8. O dashboard mostra o histórico das sessões e o sinal capturado.

## Arquivos principais

```text
.
├── wearable_tutor.py        # Código principal do monitoramento
├── estudo_db.py               # Responsável pelo banco de dados SQLite
├── dashboard_streamlit.py   # Dashboard para visualizar as sessões
├── estudo_tracker.db          # Banco criado automaticamente durante a execução
└── README.md                # Documentação do projeto
```

> Observação: o código principal do projeto está no arquivo `wearable_tutor.py`. Caso ele seja renomeado para `main.py`, basta ajustar o comando de execução.

## Tecnologias utilizadas

* Python
* ESP32
* Bluetooth Low Energy
* SQLite
* Streamlit
* Pandas

## Instalação

Crie o ambiente virtual:

```bash
python -m venv .venv
```

Ative o ambiente virtual:

### Windows

```bash
.venv\Scripts\activate
```

### Linux/macOS

```bash
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install bleak aiohttp streamlit pandas altair streamlit-autorefresh
```

## Como executar

### 1. Executar o monitor principal

```bash
python wearable_tutor.py
```

Esse comando inicia a busca pelo smartwatch e começa o monitoramento das sessões de estudo.

Durante a execução, o terminal mostra os dispositivos Bluetooth encontrados, o sinal RSSI e o estado da sessão.

### 2. Executar o dashboard

Em outro terminal, com o ambiente virtual ativado, execute:

```bash
streamlit run dashboard_streamlit.py
```

O dashboard mostra:

* tempo total focado no dia;
* sessões concluídas;
* sessões interrompidas;
* gráfico do sinal RSSI;
* histórico das sessões.

## Integração com o ESP32

O ESP32 deve estar conectado à mesma rede Wi-Fi do computador.

O monitor envia requisições HTTP para o ESP32 usando duas rotas:

```text
/leve
/forte
```

A rota `/leve` pode ser usada para indicar início de sessão ou pequenas notificações.

A rota `/forte` pode ser usada para indicar o fim de uma sessão de estudos.

## Banco de dados

O projeto utiliza SQLite para salvar os dados localmente.

O banco é criado automaticamente com o nome:

```text
estudo_tracker.db
```

Ele armazena:

* logs do sinal Bluetooth;
* início e fim das sessões;
* tempo total focado;
* status da sessão, indicando se foi concluída ou interrompida.

## Objetivo do projeto

O objetivo do **Wearable Tutor** é demonstrar uma aplicação prática de computação ubíqua, usando sensores, dispositivos vestíveis e microcontroladores para criar um ambiente inteligente de apoio ao estudo.

O sistema busca identificar o contexto do usuário de forma automática e oferecer feedback visual sem exigir interação direta constante.
