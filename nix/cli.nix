{
  lib,
  runCommand,
  writeText,
  makeWrapper,
  python3,
  original,
  sdk,
  emptyCache,
  fontConfig,
  nix,
  gh,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
let
  integration = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      (lib.fileset.fileFilter (file: file.hasExt "py") ../anki_purifier)
      (lib.fileset.fileFilter (file: file.hasExt "py") ../native)
      (lib.fileset.fileFilter (file: file.hasExt "nix") ./.)
    ];
  };
  bootstrap = writeText "anki-purifier-main.py" "import os,runpy,sys; sys.path.insert(0, ${builtins.toJSON integration}); sys.argv[0]=os.environ['ANKI_PURIFIER_COMMAND']; runpy.run_module('anki_purifier.main',run_name='__main__')";
  realize = writeText "anki-purifier-realize.nix" ''
    { lockPath, projectPath, target ? "environment" }:
    let
      pkgs = import (builtins.storePath "${nixpkgsSrc}") {};
      scope = import ${integration}/nix/scope.nix {
        inherit pkgs;
        nixpkgsSrc = builtins.storePath "${nixpkgsSrc}";
        purifierSrc = builtins.storePath "${purifierSrc}";
      };
      lockFile = builtins.toPath lockPath;
      src = if target == "environment" then builtins.toPath projectPath else builtins.path {
        path = builtins.toPath projectPath;
        name = "anki-project";
        filter = path: type: !(builtins.elem (baseNameOf path) [ ".git" ".anki-purifier" "__pycache__" "result" "output" ]);
      };
      build = scope.buildAnkiProject { inherit src lockFile; };
    in if target == "environment" then scope.environment { lock = scope.readLock { inherit src lockFile; }; }
       else if target == "project" then build.packages.project
       else if target == "release" then build.release
       else throw "Unknown ANKI purifier target"
  '';
in
runCommand "anki-purifier" { nativeBuildInputs = [ makeWrapper ]; } ''
  mkdir -p "$out/bin"
  for name in anki-purifier anki; do
    makeWrapper ${python3}/bin/python "$out/bin/$name" \
      --add-flags ${bootstrap} \
      --set ANKI_PURIFIER_COMMAND "$name" \
      --set ANKI_PURIFIER_NATIVE ${integration}/native \
      --set ANKI_PURIFIER_ORIGINAL ${original} \
      --set ANKI_PURIFIER_HOOKS ${integration}/native/hooks \
      --set ANKI_PURIFIER_SDK ${sdk} \
      --set ANKI_PURIFIER_CACHE ${emptyCache} \
      --set ANKI_PURIFIER_FONTS ${fontConfig} \
      --set ANKI_PURIFIER_REALIZE ${realize} \
      --set-default ANKI_PURIFIER_GH ${gh}/bin/gh \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set-default NIX_SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --prefix PATH : ${
        lib.makeBinPath [
          nix
          gh
        ]
      }
  done
''
