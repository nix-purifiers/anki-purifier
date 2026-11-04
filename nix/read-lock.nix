{ lib }:
{
  src,
  lockFile ? src + "/anki-purifier.lock.json",
}:
let
  raw = if builtins.pathExists lockFile then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  entries = data.entries or [ ];
  selection =
    if builtins.pathExists (src + "/anki-purifier.json") then
      builtins.fromJSON (builtins.readFile (src + "/anki-purifier.json"))
    else
      null;
  valid =
    (data.version or null) == 1
    && (data.purifier or null) == "anki"
    && builtins.isString (data.sdk or null)
    && builtins.isAttrs (data.selection or null)
    && data.selection == selection
    && builtins.isList (data.selection.addons or null)
    && builtins.all (id: builtins.isInt id && id > 0) data.selection.addons
    && builtins.length (lib.unique data.selection.addons) == builtins.length data.selection.addons
    && builtins.isAttrs (data.native.metadata or null)
    && builtins.isList entries
    && builtins.all (
      entry:
      builtins.isAttrs entry
      && builtins.isAttrs (entry.anki or null)
      && builtins.isInt (entry.anki.id or null)
      && entry.anki.id > 0
      && (entry.path or null) == "${toString entry.anki.id}.ankiaddon"
      && builtins.isString (entry.url or null)
      && lib.hasPrefix "https://" entry.url
      && builtins.isString (entry.hash or null)
      && builtins.match "sha256-[A-Za-z0-9+/]{43}=" entry.hash != null
      && builtins.isList (entry.mirrors or null)
      && builtins.all builtins.isString entry.mirrors
      && builtins.isString (entry.anki.filename or null)
      && builtins.all (key: builtins.isInt (entry.anki.${key} or null)) [
        "mod_time"
        "min_point_version"
        "max_point_version"
        "branch_index"
      ]
      && builtins.isAttrs (data.native.metadata.${toString entry.anki.id} or null)
    ) entries
    && builtins.length (lib.unique (map (entry: entry.path) entries)) == builtins.length entries
    &&
      builtins.sort builtins.lessThan (map (entry: entry.anki.id) entries)
      == builtins.sort builtins.lessThan data.selection.addons;
in
{
  purifier = "anki";
  inherit data entries;
  problems = lib.optional (
    !valid
  ) "Anki lock is missing, malformed, or stale; run anki-purifier lock --update";
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}
