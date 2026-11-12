# GCP Analytics RAG: MCP server

An MCP server, built with [FastMCP](https://gofastmcp.com), that lets Claude Code (or any MCP client) search the
Google Cloud Data Analytics course through the retrieval system of
[`GCP-ANALYTICS_RAG`](https://github.com/estvn/GCP-ANALYTICS_RAG).

**Status: built, tested (31 tests) and registered in Claude Code** (`claude mcp list` shows it connected). It was run as a
separate process over stdio against the real index and the real model; [how to register it](#register-it-in-a-client).

## What it does

The RAG retrieves passages of the course: given a question it returns the chunks that answer it (hybrid search with a
Spanish/English translation fusion, bge-m3 embeddings, PostgreSQL + pgvector). It does not write the answer: a language
model does that from the chunks. This server gives the model one tool to call.

```
 Claude Code (or another MCP client)
        │  the model calls the tool, over stdio
        ▼
   MCP server  ── bge-m3 stays loaded in memory ──┐
        │                                         │
        ▼                                         │
   PostgreSQL + pgvector (container `rag-db`) ◄───┘
```

### How it works

![MCP server architecture: client, stdio process with its two tools, and the RAG package, model and database it uses](docs/diagrams/mcp-architecture.png)

The diagram is a draw.io file (`docs/diagrams/mcp-architecture.drawio`, editable at [app.diagrams.net](https://app.diagrams.net))
with its PNG export. The whole system, from the database to the client, is in the
[RAG repository](https://github.com/estvn/GCP-ANALYTICS_RAG#architecture).

### The tool: `gcp_rag_search_course`

| argument | meaning |
|---|---|
| `question` | the question, as the user asked it (1 to 2000 characters) |
| `translation` | the same question translated into the other language (English if it is in Spanish, Spanish if it is in English); the course has passages in both (1 to 2000 characters) |
| `k` | how many chunks to return, from 1 to 100 (30 by default) |

It returns a list of chunks, best first, each with `rank`, `source` (the file), `headers` (the header path) and `text`.
The first line of each chunk (path and headers) is removed from `text` because it already comes in `source` and
`headers`. The tool is marked read-only. If the search fails it answers with an error that names the kind of failure and
says what to check (the `rag-db` container and the model files); the detail goes to the server log (stderr), never to the
client, so no host or password can leak through it.

The translation is a required argument on purpose: the retrieval technique that won the experiments searches the question
and its translation and fuses both rankings, and the RAG does not translate. The language model that calls the tool
writes the translation, so no translation model is needed.

### The help tool: `gcp_rag_check_setup`

No arguments. A new Claude session can call it to find out whether a search will work: it checks that the three files of
the model in use are in the model folder and that the database answers with a non-empty index, and it returns `ready`, one check per
piece with its detail, and a guide with where to get what is missing (the same links as the section below). The server
tells the model to call it when a search fails. A failure never reveals the database host or password to the client: the
detail stays in the server log.

## Commands: install and change the model

Besides the server, the package has commands to install the model and its database and to change them later. Run them with
the Python of this repository (`uv run python -m gcp_rag_mcp <command>`); with no command the same module runs the MCP
server, which is what the clients start.

| command | what it does |
|---|---|
| `setup` | First install. Explains the two models, **asks which one you want**, then downloads that model's files into `../rag/models/<model>/`, pulls the database image already loaded with the course indexed by that model, starts it and remembers the choice. `setup --model e5-small` skips the question. |
| `switch` | Changes to the other model: downloads its files and its database image, stops the other database (its container and volume are kept, so switching back is instant) and remembers the choice. `switch --model bge-m3` skips the question. **Restart the MCP server afterwards** (`/mcp` in Claude Code, or open a new session): the client keeps the old model until then. If the download or the database fails, the previous choice stays. |
| `status` | Shows the model in use and whether its files and its database are ready; exits with 1 if something is missing. |
| `help` | Lists these commands. `python -m gcp_rag_mcp --help` also works. |

The two models, and what each one downloads (the model file is checked against its SHA-256; the database image holds the
index built with that same model, so the vectors always match):

| model | files, from a pinned revision | size | database image (database) | vectors |
|---|---|---|---|---|
| `bge-m3` (default, best ranking in experiment E33) | `onnx/model_int8.onnx`, `tokenizer.json`, `config.json` from [onnx-community/bge-m3-ONNX](https://huggingface.co/onnx-community/bge-m3-ONNX) at `25b9af8e` | 559 MB, about 1.1 GB of RAM loaded | `ghcr.io/estvn/gcp-rag-db:bge-m3` (`courses_bge`) | 1024 |
| `e5-small` (light) | `onnx/model_quantized.onnx`, `tokenizer.json`, `config.json` from [Xenova/multilingual-e5-small](https://huggingface.co/Xenova/multilingual-e5-small) at `761b726d` | 130 MB | `ghcr.io/estvn/gcp-rag-db:e5-small` (`courses_e5`) | 384 |

Each model has its own container (`rag-db-bge`, `rag-db-e5`) and volume. Both publish the port 5433, so starting one stops the
other (and the old `rag-db`, if it is running); nothing is ever deleted. To pick the model for one run without changing the
saved choice, set `RAG_MODEL=bge-m3` or `RAG_MODEL=e5-small` in the client's `env`: it wins over the saved choice. The saved
choice is the file `~/.gcp-rag-mcp/preferences.json` (folder changeable with `RAG_MCP_HOME`).

`./setup.sh` is the bootstrap for a machine with nothing: it clones the RAG repository next to this one and runs `uv sync`
(the `setup` command needs both), then runs `setup`. `./setup.sh --model e5-small` passes the model through and
`./setup.sh --check` runs `status`. It needs `git`, `uv` and `podman`.

## Use it

Requirements: the RAG repository next to this one (`../rag`, installed as an editable dependency), the PostgreSQL
container `rag-db` running with the index `courses_bge`, and the bge-m3 files in `../rag/models/bge-m3`. Where to get
each piece is in [Setup: what to download and start](#setup-what-to-download-and-start).

```bash
uv sync
uv run pytest                     # 31 tests; the integration test needs the database and the model
uv run python -m gcp_rag_mcp      # starts the server over stdio (an MCP client normally does this)
```

## Register it in a client

The server is started by the client, not by hand: the client launches the command below as a child process and talks to
it over stdio. Use the Python of this repository's virtual environment (`uv sync` creates `.venv`); replace
`<repo>` with the absolute path of this repository (forward slashes work on Windows).

**Claude Code** (command; registered for this machine's user, and checked with `claude mcp list`):

```bash
claude mcp add gcp-rag --scope user -- "<repo>/.venv/Scripts/python.exe" -m gcp_rag_mcp
```

**Claude Code** (manual JSON, in `~/.claude.json` for the user scope or `.mcp.json` of a project):

```json
{
  "mcpServers": {
    "gcp-rag": {
      "command": "<repo>/.venv/Scripts/python.exe",
      "args": ["-m", "gcp_rag_mcp"]
    }
  }
}
```

**OpenCode** (manual JSON, in `opencode.json`; its format differs: `command` is one array):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "gcp-rag": {
      "type": "local",
      "command": ["<repo>/.venv/Scripts/python.exe", "-m", "gcp_rag_mcp"],
      "enabled": true
    }
  }
}
```

On Linux or macOS the interpreter is `<repo>/.venv/bin/python`. To change the database or the model folder, add the
variables of the next table: `"env": {...}` in Claude Code, `"environment": {...}` in OpenCode.

## What starts what

The client starts **the server only**. The server does not start the database, and it does not need to know where the
RAG repository is in order to run:

- **The code of the RAG** is found because `rag` is an editable dependency (`../rag`) installed in this `.venv`; the
  client runs this `.venv`'s Python, so `import rag` works from any working directory.
- **The model** (`models/bge-m3`) is found from the location of that same installed package, and loads on the first
  search, not at start-up.
- **The database** is reached by URL (`127.0.0.1:5433`), so the container `rag-db` has to be running already
  (`podman start rag-db`). If it is not, the tool answers with an error that says so.

## Setup: what to download and start

A search needs five things. Only the database container has to be started by hand.

| piece | where to get it | how |
|---|---|---|
| this server | [estvn/GCP-ANALYTICS_RAG_MCP](https://github.com/estvn/GCP-ANALYTICS_RAG_MCP) | `git clone`, then `uv sync` |
| the RAG code (retrieval, chunker, store) | [estvn/GCP-ANALYTICS_RAG](https://github.com/estvn/GCP-ANALYTICS_RAG), cloned **next to** this repository as `../rag` | `git clone`; it is installed here as an editable dependency |
| the index (PostgreSQL 17 + pgvector, database `courses_bge`) | image `ghcr.io/estvn/gcp-rag-db:bge-m3` (public; `:e5-small` is the light variant, database `courses_e5`) | see below |
| the bge-m3 model, int8 ONNX | [onnx-community/bge-m3-ONNX](https://huggingface.co/onnx-community/bge-m3-ONNX) | download `onnx/model_int8.onnx`, `tokenizer.json` and `config.json` into `../rag/models/bge-m3/` (`onnx/model_int8.onnx` there) |
| Claude Code or OpenCode | | [register the server](#register-it-in-a-client) |

**All in one command.** `./setup.sh` (Git Bash on Windows, or any Linux or macOS shell) clones the RAG repository next to
this one, runs `uv sync` and then the `setup` command, which asks which model you want and does the rest (model files with
their SHA-256 check, database image, container). It leaves alone what is already there. See
[Commands](#commands-install-and-change-the-model). The commands were tested with stand-ins for Hugging Face and Podman, the
model download was run for real for `e5-small` and the pinned URLs and hashes of both models were checked against Hugging
Face; creating a container from the published `e5-small` image was not run on a clean machine.

```bash
podman run -d --name rag-db -p 127.0.0.1:5433:5432 -v rag_pgdata:/var/lib/postgresql/data   ghcr.io/estvn/gcp-rag-db:bge-m3        # first time: restores the index, a few seconds
podman start rag-db                      # the next times (and `podman machine start` first if Podman is stopped)
```

The `model_int8.onnx` used here and the one in that Hugging Face repository have the same SHA-256 (`2237f770...`). The image holds the index and not the model, and the index must be
queried with the model it was built with (bge-m3 for `:bge-m3`, e5-small for `:e5-small`); the server uses the model chosen
with `setup` or `switch`.

### What must be ready for a search to work

A search needs both the model and the database; the difference is who puts them in place.

| piece | needed for a search | who starts it | how to check |
|---|---|---|---|
| PostgreSQL container `rag-db` (index `courses_bge`) | yes | **you**, before opening the client: `podman machine start` if Podman is stopped, then `podman start rag-db` | `podman ps` lists `rag-db` |
| bge-m3 model | yes | **the server**, on the first search (a few seconds, about 1.1 GB of RAM; it stays loaded while the session lasts) | its files exist in `../rag/models/bge-m3` (git-ignored: download them again on a new machine) |
| the MCP server | yes | **the client**, when the session opens | `claude mcp list` shows `gcp-rag` connected |
| `.venv` of this repository | yes | `uv sync`, once | `.venv/Scripts/python.exe` exists |

"Connected" in `claude mcp list` only proves that the server process started: the database and the model are first
touched by the first search, so a stopped container shows up as an error on the first question, not before.

Three environment variables change what it uses, if the defaults do not fit:

| variable | default |
|---|---|
| `RAG_MODEL` | the model saved by `setup` or `switch`, or `bge-m3` if none was chosen. Picks the model, its database and its files together; `bge-m3` or `e5-small` |
| `RAG_DATABASE_URL` | `postgresql://rag:rag@127.0.0.1:5433/courses_bge?connect_timeout=5` (the index of the winning configuration with the GCP and Power BI courses, local credentials; with the database down the tool fails in 5 seconds) |
| `RAG_MODEL_DIR` | the `models/bge-m3` folder of the RAG repository |

## Examples

Real calls through the server over stdio (first three chunks of each answer, `k=5`):

| question | best chunk (source > headers) |
|---|---|
| ¿Qué diferencia hay entre una tabla particionada y una agrupada en BigQuery? | `016_CREATE_PARTITIONED_TABLE.md` > Crea una tabla particionada |
| ¿Para qué sirve Dataproc? | `022_HOW_TO_MANAGE_DATAPROC_CLUSTERS.md` > Cómo administrar clústeres de Dataproc; then `020_KEY_PROCESSES_BENEFITS_DATAPROC.md` |
| ¿Cómo se crea un panel de control en Looker Studio? | `014_GUIDE_LOOKER_STUDIO.md` > Guía para Looker Studio > Cómo ver y crear un informe |

The first question mixes two concepts (partitioned and clustered): the top three chunks are all about partitioning, so
a model should ask again or use a larger `k` to cover the clustered side. This is one reason to keep `k` at 30.

## What was measured

Through the real protocol: the server as a separate process over stdio, started from another working directory, with
questions of the evaluation set and their translations, on an idle machine:

| | result |
|---|---|
| start and initialise the server | 4.5 s |
| **first question** (loads the model and opens the database) | **3.3 s** |
| **following questions**, 30 chunks | **0.11 to 0.14 s** |
| memory of the server process after loading | 1,213 MB, and 1,215 MB after 7 questions |

The retrieval alone, inside Python on a busier machine, took 424 ms in the median (E34 of the RAG repository), so the
time of a question depends on how loaded the machine is; what does not change is that the first one pays for the load
and the rest do not.

## Why an MCP server and not "raw"

"Raw" means using the RAG without a server: a command or script that loads the library, answers one question and exits,
whose output the model reads (pasted by hand, or run by Claude Code through its shell tool), or a script that calls an
LLM API with the chunks.

| | paste the chunks by hand | command run through the shell | script that calls an LLM API | **MCP server** |
|---|---|---|---|---|
| effort to build | a search command is needed | low | medium (key, dependency) | medium (server and tests) |
| time per question | about 6 s or more | about 6 s or more | about 6 s or more | **0.1 s after the first** |
| the model can call it by itself | no | only if told how | yes | **yes, it discovers the tool** |
| works in clients without a shell | yes | no | only that script | **any MCP client** |
| extra cost per question | none | none | **money (API)** | none |

1. **The model stays loaded.** A command is a new process for every question: it imports the libraries, reads the
   543 MB bge-m3 file into memory (5.6 s measured in the RAG repository), connects to the database, answers and exits,
   freeing everything. The server is one process that lives while the client session is open: it loads the model on the
   first question and every later question reuses it. The "about 6 s" of a command is the load time plus the query; the
   start-up of Python and the database connection were not measured apart from it, so it is a lower bound.
2. **The model discovers the tool and its arguments.** An MCP client lists the tools with their description and typed
   parameters. With a shell command the model has to be told that the command exists and how to call it.
3. **The model writes the translation** (see above), so no translation model has to be installed.
4. **A narrow permission.** The client asks permission for one read-only tool; running a shell command needs permission
   to run commands in general.
5. **It works where there is no shell.** Some MCP clients, such as Claude Desktop, call tools but do not run commands
   (general knowledge, not tested here).
6. **A structured answer.** Each chunk comes with its file, its headers and its text.
7. **It can grow.** More tools can be added later, for example reading a whole section of a document.

### What it costs

- It has to be built and maintained: this repository, with FastMCP and the `rag` package (117 packages in total).
- **While the client session is open the process keeps about 1.2 GB of RAM** once the first question loaded the model,
  even if nobody asks anything. Loading on the first question and not at start-up means it costs nothing until then.
- For occasional use a command run through the shell is almost as good and much cheaper to build.

## Conformance with the MCP builder standards

Applied: server name `gcp_rag_mcp`; tool name `{service}_{action}_{resource}`; the four annotations; Pydantic limits on
every argument with descriptions; actionable errors without internal detail; logs on stderr only (stdout is the
protocol); boundary tests (k at 1, 100, 0 and 101; empty and over-long text); timeout on the database connection.

Deliberately not applied:

- **Async tool.** The tool is sync: the search is CPU-bound ONNX and a blocking `psycopg` call; FastMCP runs it in a
  thread pool, and a lock keeps one search at a time.
- **Markdown output.** JSON only: the caller is a model that cites `source` and `headers`.
- **Pagination.** `k` bounds the answer (at most 100 chunks); a second page would only mean a bigger `k`.
- **Lifespan.** The model loads lazily on the first search instead, so an idle server costs nothing.
- **`tools/` folder.** Two small tools; see the decisions below.
- **pytest-asyncio.** The `anyio` pytest plugin that comes with FastMCP's dependencies is used.
- **Credentials.** The default URL holds local development credentials of a container on `127.0.0.1`; use
  `RAG_DATABASE_URL` for anything else.

## Decisions taken

- **FastMCP 4.1.3, pinned.** It was 18 days old when chosen; the newest release (4.1.6) was 4 days old and this series
  is published every few days.
- **Two tools.** `gcp_rag_search_course` and the read-only `gcp_rag_check_setup`; more can be added when there is a use for them. For that reason the code is flat
  (`server.py`) and has no `tools/` folder yet: a sub-package for a single tool would be clutter.
- **The model is loaded on the first question**, with the database connection. If a search fails, the connection is
  closed and reopened on the next one; the model is kept.
- **One search at a time.** The connection is not meant to be shared by two searches at once, so a lock serialises them.
- **The `rag` package is a path dependency** (`../rag`, editable): both repositories have to sit side by side. A Git
  dependency would remove that, but the RAG repository has no release to pin yet.
- **Defaults of the RAG are kept:** bge-m3 and 30 chunks per answer. The pool of candidates per search (100 in the code,
  30 in the measurements of the RAG repository) is still to be settled there; this server does not set it.
- **No relevance threshold.** The scores of the fusion are positions, not calibrated similarities, so there is no sound
  number to cut at; the server returns the best `k` chunks and the model judges whether they answer.

## Layout

```
src/gcp_rag_mcp/
├── __main__.py     # python -m gcp_rag_mcp: runs the server over stdio, or a command if it gets arguments
├── cli.py          # the commands: setup, switch, status, help
├── catalog.py      # the two models: source, pinned revision, SHA-256, database image, container
├── preferences.py  # the model chosen with setup or switch, saved in a small file
├── downloads.py    # download_model: model files from Hugging Face, checked against their SHA-256
├── database.py     # ensure_database: starts the Podman container of a model, stops the other
├── config.py       # Settings: model, database and model folder, from the environment and the saved choice
├── retriever.py    # LazyRetriever: loads the model and the connection on the first search
├── setup_check.py  # run_checks: model files and database, and the setup guide for the help tool
└── server.py       # create_server: the FastMCP server and its tool
tests/              # mirrors src/; test_integration.py needs the database and the model
docs/diagrams/      # architecture diagram (.drawio and .png)
pyproject.toml
README.md
```

## Checks run

- 60 tests: the tool, its arguments, its limits and its errors through FastMCP's in-memory client; the lazy loading and the
  reconnection with stand-ins; the settings and the model choice; the commands, the download (hash check, damaged files,
  nothing half downloaded) and the container handling with stand-ins; and two tests with the real model and index.
- Bandit (no issues), pip-audit on the pinned dependencies (no known vulnerabilities) and detect-secrets (none), and Ruff.

## What is not proven yet

- **That Claude Code uses it well.** It is registered and connects, but it has not been tried yet with real questions in Spanish.
- **That a language model answers well with these chunks.** The golden-set experiments of the RAG repository measure
  where the correct chunk ranks, not the quality of a generated answer. Using this server from Claude Code with real
  questions in Spanish is how that gets tested.
