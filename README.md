# GCP Analytics RAG: MCP server

An MCP server, built with [FastMCP](https://gofastmcp.com), that lets Claude Code (or any MCP client) search the
Google Cloud Data Analytics course through the retrieval system of
[`GCP-ANALYTICS_RAG`](https://github.com/estvn/GCP-ANALYTICS_RAG).

**Status: built, tested (24 tests) and registered in Claude Code** (`claude mcp list` shows it connected). It was run as a
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

## Use it

Requirements: the RAG repository next to this one (`../rag`, installed as an editable dependency), the PostgreSQL
container `rag-db` running with the index `full_SEMH_bge`, and the bge-m3 files in `../rag/models/bge-m3`.

```bash
uv sync
uv run pytest                     # 24 tests; the integration test needs the database and the model
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

### What must be ready for a search to work

A search needs both the model and the database; the difference is who puts them in place.

| piece | needed for a search | who starts it | how to check |
|---|---|---|---|
| PostgreSQL container `rag-db` (index `full_SEMH_bge`) | yes | **you**, before opening the client: `podman machine start` if Podman is stopped, then `podman start rag-db` | `podman ps` lists `rag-db` |
| bge-m3 model | yes | **the server**, on the first search (a few seconds, about 1.1 GB of RAM; it stays loaded while the session lasts) | its files exist in `../rag/models/bge-m3` (git-ignored: download them again on a new machine) |
| the MCP server | yes | **the client**, when the session opens | `claude mcp list` shows `gcp-rag` connected |
| `.venv` of this repository | yes | `uv sync`, once | `.venv/Scripts/python.exe` exists |

"Connected" in `claude mcp list` only proves that the server process started: the database and the model are first
touched by the first search, so a stopped container shows up as an error on the first question, not before.

Two environment variables change where it looks, if the defaults do not fit:

| variable | default |
|---|---|
| `RAG_DATABASE_URL` | `postgresql://rag:rag@127.0.0.1:5433/full_SEMH_bge?connect_timeout=5` (the index of the winning configuration, local credentials; with the database down the tool fails in 5 seconds) |
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
- **`tools/` folder.** One tool; see the decisions below.
- **pytest-asyncio.** The `anyio` pytest plugin that comes with FastMCP's dependencies is used.
- **Credentials.** The default URL holds local development credentials of a container on `127.0.0.1`; use
  `RAG_DATABASE_URL` for anything else.

## Decisions taken

- **FastMCP 4.1.3, pinned.** It was 18 days old when chosen; the newest release (4.1.6) was 4 days old and this series
  is published every few days.
- **One tool.** `gcp_rag_search_course`; more can be added when there is a use for them. For that reason the code is flat
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
├── __main__.py     # python -m gcp_rag_mcp: builds the server and runs it over stdio
├── config.py       # Settings: database and model folder, from the environment
├── retriever.py    # LazyRetriever: loads the model and the connection on the first search
└── server.py       # create_server: the FastMCP server and its tool
tests/              # mirrors src/; test_integration.py needs the database and the model
pyproject.toml
README.md
```

## Checks run

- 24 tests: the tool, its arguments, its limits and its errors through FastMCP's in-memory client; the lazy loading and the
  reconnection with stand-ins; the settings; and one test with the real model and index.
- Bandit (no issues), pip-audit on the pinned dependencies (no known vulnerabilities) and detect-secrets (none), and Ruff.

## What is not proven yet

- **That Claude Code uses it well.** It is registered and connects, but it has not been tried yet with real questions in Spanish.
- **That a language model answers well with these chunks.** The golden-set experiments of the RAG repository measure
  where the correct chunk ranks, not the quality of a generated answer. Using this server from Claude Code with real
  questions in Spanish is how that gets tested.
