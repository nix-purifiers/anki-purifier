{
  lib,
  runCommand,
  writeText,
  fetchurl,
  fetchgit,
  python3,
  original,
  purifier,
  sdk,
  fontConfig,
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  archives = purifier.tree (
    {
      name = "anki-addon-archives";
      entries = checked.entries;
      inherit
        runCommand
        writeText
        fetchurl
        fetchgit
        python3
        ;
    }
    // fetchers
  );
  request = writeText "anki-native-install.json" (
    builtins.toJSON {
      action = "install";
      entries = checked.entries;
      metadata = checked.data.native.metadata;
      archives = builtins.listToAttrs (
        map (entry: {
          name = entry.path;
          value = "${archives}/${entry.path}";
        }) checked.entries
      );
    }
  );
  driver = lib.fileset.toSource {
    root = ../native;
    fileset = lib.fileset.unions [
      ../native/anki_purifier_helper.py
      ../native/anki_purifier_install_request.py
      ../native/hooks/sitecustomize.py
    ];
  };
in
assert lib.assertMsg (checked.data.sdk == sdk) "Anki SDK changed; run anki-purifier lock --update";
runCommand "anki-locked-addons" { } ''
  export HOME="$TMPDIR/home" XDG_CONFIG_HOME="$TMPDIR/config" XDG_DATA_HOME="$TMPDIR/data" XDG_CACHE_HOME="$TMPDIR/cache" XDG_RUNTIME_DIR="$TMPDIR/runtime"
  mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$XDG_RUNTIME_DIR" "$out"
  chmod 700 "$XDG_RUNTIME_DIR"
  export QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1 PYTHONNOUSERSITE=1
  export FONTCONFIG_FILE=${fontConfig} ANKI_PURIFIER_REQUEST="$TMPDIR/request.json"
  ${python3}/bin/python ${driver}/anki_purifier_install_request.py ${request} "$out" "$ANKI_PURIFIER_REQUEST"
  export PYTHONPATH=${driver}/hooks PYTHONPYCACHEPREFIX="$TMPDIR/python-cache"
  export ANKI_PURIFIER_HELPER=${driver}/anki_purifier_helper.py ANKI_PURIFIER_RESPONSE="$TMPDIR/response.json"
  ${original}/bin/anki --version > "$TMPDIR/native.log"
  # Native Anki can serialize identical metadata with different key order.
  # Canonicalize only its generated declared add-on metadata after installation.
  ${python3}/bin/python -I - ${request} "$out" <<'PY_META'
  import json
  import sys
  from pathlib import Path
  request = json.loads(Path(sys.argv[1]).read_text())
  for entry in request["entries"]:
      path = Path(sys.argv[2]) / "addons" / str(entry["anki"]["id"]) / "meta.json"
      native = json.loads(path.read_text())
      path.write_text(json.dumps(native, sort_keys=True) + "\n")
      assert json.loads(path.read_text()) == native
  PY_META
  ln -s ${writeText "anki-lock.json" (builtins.toJSON checked.data)} "$out/lock.json"
''
