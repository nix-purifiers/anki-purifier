{
  lib,
  purifier,
  runCommand,
  python3,
  original,
  environment,
  readLock,
  emptyCache,
  fontConfig,
  gnutar,
  gzip,
}:
{
  src,
  lockFile ? src + "/anki-purifier.lock.json",
  script ? "build.py",
  fetchers ? { },
  doCheck ? false,
  checkCommand ? "",
  resourceRoots ? { },
  resourceDependencies ? [ ],
}:
let
  lock = readLock { inherit src lockFile; };
  profile = environment { inherit lock fetchers; };
  driver = lib.fileset.toSource {
    root = ../native;
    fileset = lib.fileset.unions [
      ../native/anki_purifier_run_project.py
      ../native/anki_purifier_prepare.py
      ../native/anki_purifier_seed_profile.py
      (lib.fileset.fileFilter (file: file.hasExt "py") ../native/hooks)
    ];
  };
  projectSource = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        ".git"
        ".anki-purifier"
        "__pycache__"
        "result"
        "output"
      ]);
  };
  builtProject = runCommand "anki-project" { } ''
    export ANKI_PURIFIER_ENVIRONMENT=${profile} ANKI_PURIFIER_ORIGINAL=${original}
    export ANKI_PURIFIER_HOOKS=${driver}/hooks ANKI_PURIFIER_CACHE=${emptyCache} ANKI_PURIFIER_FONTS=${fontConfig}
    export ANKI_PURIFIER_OUTPUT="$out" ANKI_PURIFIER_RUN_STATE="$TMPDIR/anki-run"
    export QTWEBENGINE_DISABLE_SANDBOX=1
    mkdir -p "$out"
    cp -r ${projectSource} project
    chmod -R u+w project
    cd project
    export ANKI_PURIFIER_PROJECT="$PWD" ANKI_PURIFIER_SCRIPT="$PWD/"${lib.escapeShellArg script}
    ${python3}/bin/python ${driver}/anki_purifier_run_project.py
    ${lib.optionalString doCheck checkCommand}
  '';
  projections = lib.optionalAttrs (resourceRoots != { }) (
    purifier.resourceProjections {
      producer = builtProject;
      roots = resourceRoots;
      dependencies = resourceDependencies;
      inherit runCommand python3;
    }
  );
  project = builtProject // {
    inherit projections;
  };
  release =
    runCommand "anki-project-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        mkdir -p "$out"
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -cf - -C ${project} . | gzip -n > "$out/anki-project.tar.gz"
      '';
in
{
  packages = {
    default = project;
    inherit project;
    environment = profile;
  };
  tests = project;
  inherit release projections;
  fetches = lock.entries;
}
