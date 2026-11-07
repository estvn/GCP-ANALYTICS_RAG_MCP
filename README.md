# GCP Analytics RAG: MCP server

**Status: not built yet.** This repository only holds this document for now. It explains why the retrieval system of
[`GCP-ANALYTICS_RAG`](https://github.com/estvn/GCP-ANALYTICS_RAG) will be exposed through an MCP server and not used
"raw", and what is still undecided.

## What it is for

The RAG repository retrieves passages of the Google Cloud Data Analytics course: given a question it returns the
chunks that answer it (hybrid search with a Spanish/English translation fusion, bge-m3 embeddings, PostgreSQL +
pgvector). It does not write the answer: a language model does that from the chunks. This server will give the model a
tool to call, so that Claude Code (or any other MCP client) can search the course by itself.

```
 Claude Code (or another MCP client)
        │  the model calls the tool, over stdio
        ▼
   MCP server  ── bge-m3 stays loaded in memory ──┐
        │                                         │
        ▼                                         │
   PostgreSQL + pgvector (container `rag-db`) ◄───┘
```

## Why an MCP server and not "raw"

"Raw" means using the RAG without a server: a command or script that loads the library, answers one question and exits,
whose output the model reads (pasted by hand, or run by Claude Code through its shell tool), or a script that calls an
LLM API with the chunks.

| | paste the chunks by hand | command run through the shell | script that calls an LLM API | **MCP server** |
|---|---|---|---|---|
| effort to build | a search command is needed | low | medium (key, dependency) | medium (server and tests) |
| time per question | about 6 s or more | about 6 s or more | about 6 s or more | **about 0.4 s** |
| the model can call it by itself | no | only if told how | yes | **yes, it discovers the tool** |
| works in clients without a shell | yes | no | only that script | **any MCP client** |
| extra cost per question | none | none | **money (API)** | none |

The reasons, in order of weight:

1. **The model stays loaded.** A command is a new process for every question: it imports the libraries, reads the
   543 MB bge-m3 file into memory (5.6 s measured), connects to the database, answers and exits, freeing everything. A
   server is one process that lives while the client session is open: it loads the model once and every later question
   reuses it. Measured in the RAG repository, in-process: `search_many` with two phrasings takes 424 ms in the median
   (557 ms p95). The 6 seconds of a command is the load time plus the query; the start-up of Python and the database
   connection were not measured separately, so it is a lower bound.
2. **The model discovers the tool and its arguments.** An MCP client lists the tools with their description and typed
   parameters (question, translation, number of chunks). With a shell command the model has to be told that the command
   exists and how to call it.
3. **The model writes the translation.** The retrieval technique that won the experiments searches the question and its
   translation and fuses both rankings; the RAG repository does not translate. With a tool the language model that is
   calling it supplies both phrasings as arguments, so no translation model has to be installed (which a local
   alternative would need, with its memory and the risk of a worse translation than the one evaluated).
4. **A narrow permission.** The client asks permission for one read-only tool. Running a shell command needs permission
   to run commands in general.
5. **It works where there is no shell.** Some MCP clients, such as Claude Desktop, call tools but do not run commands
   (general knowledge, not tested here).
6. **A structured answer.** Each chunk comes with its file, its headers and its text, and the server can apply a
   relevance threshold and answer "nothing relevant" instead of returning weak matches (this was in the first
   specification).
7. **It can grow.** More tools can be added later, for example reading a whole section of a document.

## What it costs

- It has to be built and maintained: a stdio server with the official `mcp` SDK, with tests.
- **While the client session is open the process keeps about 1.1 GB of RAM** (1,135 MB after loading bge-m3, E35 of the
  RAG repository; it does not grow with the queries) even if nobody asks anything. Loading the model on the first question
  and not at start-up avoids paying it until it is needed.
- For occasional use a command run through the shell is almost as good and much cheaper to build.

## What is not proven yet

- **The protocol overhead.** The 0.4 s is the retrieval measured inside Python; the round trip through MCP was not
  measured.
- **That a language model answers well with these chunks.** The golden-set experiments of the RAG repository measure
  where the correct chunk ranks, not the quality of a generated answer. Building this server is also how that gets
  tested, with real questions in Spanish.

## Planned design (not implemented, decisions pending)

- **Transport and library:** stdio, with the official `mcp` Python SDK (it is not installed yet).
- **Tools (names are not final):** a search tool taking the question, its translation and the number of chunks, and
  returning each chunk with its source file, headers and text; possibly a second tool to read a section of a document.
- **Loading the model:** on the first question by default, configurable to load at start-up and to unload after some idle
  time.
- **Dependency on the RAG code:** the server needs the `rag` package, from the other repository. How to depend on it (a
  path or a Git dependency) is open.
- **Requirements at run time:** the PostgreSQL container `rag-db` running, the index built, and the bge-m3 model files
  in `models/bge-m3` of the RAG repository.
- **Defaults inherited from the RAG:** bge-m3 and 30 chunks per answer. The pool of candidates per search (100 in the code,
  30 in the measurements) is still to be settled there.

## Planned layout

```
src/<package>/{server.py, tools/}
tests/            # mirrors src/
pyproject.toml
README.md
```

## Next steps

1. Decide how the server depends on the `rag` package.
2. Build the server and its tests.
3. Try it from Claude Code with questions in Spanish and measure the whole path (protocol, search, answer).
4. Update this README with what was measured.
