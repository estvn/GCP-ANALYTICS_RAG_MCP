# GCP Analytics RAG: MCP server

An MCP server, built with [FastMCP](https://gofastmcp.com), that lets Claude Code (or any MCP client) search the
Google Cloud Data Analytics course through the retrieval system of
[`GCP-ANALYTICS_RAG`](https://github.com/estvn/GCP-ANALYTICS_RAG).

**Status: built and tested (15 tests), not tried from Claude Code yet.** It was run as a separate process over stdio
against the real index and the real model; the command to register it in Claude Code is [below](#use-it).

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

### The tool: `gcp_course_search`

| argument | meaning |
|---|---|
| `question` | the question, as the user asked it |
| `translation` | the same question translated into the other language (English if it is in Spanish, Spanish if it is in English); the course has passages in both |
| `k` | how many chunks to return, from 1 to 100 (30 by default) |

It returns a list of chunks, best first, each with `rank`, `source` (the file), `headers` (the header path) and `text`.
The tool is marked read-only. If the search fails it answers with an error that says what to check (the `rag-db`
container and the model files).

The translation is a required argument on purpose: the retrieval technique that won the experiments searches the question
and its translation and fuses both rankings, and the RAG does not translate. The language model that calls the tool
writes the translation, so no translation model is needed.

## Use it

Requirements: the RAG repository next to this one (`../rag`, installed as an editable dependency), the PostgreSQL
container `rag-db` running with the index `full_SEMH_bge`, and the bge-m3 files in `../rag/models/bge-m3`.

```bash
uv sync
uv run pytest                     # 15 tests; the integration test needs the database and the model
uv run python -m gcp_rag_mcp      # starts the server over stdio (an MCP client normally does this)
```

To register it in Claude Code (this changes your Claude Code configuration, so it is not done by this repository):

```bash
claude mcp add gcp-rag --scope user -- "<path to this repository>/.venv/Scripts/python.exe" -m gcp_rag_mcp
```

Two environment variables change where it looks, if the defaults do not fit:

| variable | default |
|---|---|
| `RAG_DATABASE_URL` | `postgresql://rag:rag@127.0.0.1:5433/full_SEMH_bge` (the index of the winning configuration, local credentials) |
| `RAG_MODEL_DIR` | the `models/bge-m3` folder of the RAG repository |

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

## Decisions taken

- **FastMCP 4.1.3, pinned.** It was 18 days old when chosen; the newest release (4.1.6) was 4 days old and this series
  is published every few days.
- **One tool.** `gcp_course_search`; more can be added when there is a use for them. For that reason the code is flat
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

- 15 tests: the tool, its arguments and its errors through FastMCP's in-memory client; the lazy loading and the
  reconnection with stand-ins; the settings; and one test with the real model and index.
- Bandit (no issues), pip-audit on the pinned dependencies (no known vulnerabilities) and detect-secrets (none), and Ruff.

## What is not proven yet

- **That Claude Code uses it well.** It was tested with FastMCP's own client over stdio, not from Claude Code.
- **That a language model answers well with these chunks.** The golden-set experiments of the RAG repository measure
  where the correct chunk ranks, not the quality of a generated answer. Using this server from Claude Code with real
  questions in Spanish is how that gets tested.
