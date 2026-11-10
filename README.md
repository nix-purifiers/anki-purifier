# anki-purifier

Use Anki with locked, Nix-resolved add-ons.

## Quickstart

Enter a shell with the wrapper:

```sh
nix shell 'github:nix-purifiers/anki-purifier'
```

Create `anki-purifier.json` in your working directory with AnkiWeb add-on IDs:

```json
{"addons": [2055492159]}
```

Lock the selection, then open Anki:

```sh
anki-purifier lock --update
anki
```

The wrapper keeps Anki's normal profiles and collections. Selected add-on code
comes from the Nix store; add-on preferences and `user_files` remain writable.
Close Anki before switching a collection to a different lock. Anki's native
collection lock prevents two processes from opening the same collection.

Without a lockfile, `anki` warns and delegates to ordinary Anki. A stale or
invalid lock fails with a repair message.

## Updating add-ons

Edit the selection and capture a new lock:

```sh
anki-purifier lock --update
```

Locked sessions disable native add-on installation, removal and update checks.
Configuration and enable/disable controls remain available. Ordinary networking,
including AnkiConnect requests, remains available.

## Scripted workflows

Run an Anki Python script after profile initialization and add-on loading:

```sh
anki-purifier run build.py
```

This command uses a separate collection in `.anki-purifier/run/profile`, leaving
your normal collection alone. Use `run --gui build.py` for a visible window.
Scripts can import `aqt` and use `aqt.mw` and the selected add-ons. Script exit
status is preserved and Anki closes through its native shutdown path.

Optional `anki-purifier.settings.json` supplies add-on configuration overrides.
For example, the included AnkiConnect fixture requests an available local port:

```json
{"2055492159": {"webBindPort": 0}}
```

The example creates a note through AnkiConnect and exports native tab-separated
text. Change `answer.json` and rerun to update the export.

```sh
cd examples/minimal
anki-purifier run build.py
cat output/notes.txt
```

## Nix builds

`buildAnkiProject` is available through the flake overlay for projects that also
want to execute an Anki script in the Nix sandbox. It provides dependency,
project and release outputs. `anki-purifier build` builds the project output;
`anki-purifier bundle` creates a normalized release archive.

## Scope

The integration uses Anki's native AnkiWeb downloader, archive installer and
metadata handling. Captured archives are hashed and fetched by Nix. Runtime
guards reject writable add-on code and freeze native code installation paths;
they do not sandbox arbitrary Python code executed by an add-on or project.

The pinned SDK is Anki 26.09.3. Native GUI, add-on and export checks run on
x86_64 Linux. The flake also configures aarch64 Linux; its runtime has not been
tested locally. Typed projection interfaces are unsupported.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).

## Public output resources

Select generated project output files explicitly:

```nix
project = pkgs.anki-purifier.buildAnkiProject {
  src = ./.;
  resourceRoots."public/file" = "generated-file";
};
```

`project.projections.resources` exposes the selected file directory and its
catalog; `project.projections.web.documentRoot` is the HTTP serving root,
and `project.projections.java-resources.classPath` is the resource JAR.
The same projections are attached to `project.packages.project`.
`resourceDependencies` accepts additional typed resource views. Empty
`resourceRoots` preserves existing output behavior.

Paths are relative to the native project output. Selection copies actual
export bytes. Unselected siblings stay outside the exported tree, and proof
metadata stays outside HTTP and JAR payloads. A selected directory includes
its contents, so select only
public generated files or directories. Missing files, traversal, and resource
collisions fail.

Checks run two genuine native producer inputs, compare every selected byte
with native files, serve them over HTTP, and load the JAR through an isolated
Java class loader with exact origin and hash checks. They exclude a real
private sibling and reject a genuine changed producer's JAR against the
original byte contract. Native producers, resource views, and consumers are
rebuilt directly.
