{
  pkgs,
  nixpkgsSrc,
  purifierSrc,
}:
pkgs.lib.makeScope pkgs.newScope (scope: {
  original = pkgs.anki;
  purifier = import (purifierSrc + "/nix/lib") { inherit (pkgs) lib; };
  buildAnkiProject = scope.callPackage ./build-project.nix { };
  cli = scope.callPackage ./cli.nix { inherit nixpkgsSrc purifierSrc; };
  readLock = import ./read-lock.nix { inherit (pkgs) lib; };
  environment = scope.callPackage ./environment.nix { };
  emptyCache = pkgs.runCommand "anki-immutable-python-cache" { } "mkdir -p $out";
  fontConfig = pkgs.makeFontsConf {
    fontDirectories = [
      pkgs.dejavu_fonts
      pkgs.noto-fonts
    ];
  };
  sdk = builtins.hashString "sha256" (
    builtins.toJSON {
      nixpkgs = toString nixpkgsSrc;
      native = builtins.listToAttrs (
        map
          (path: {
            name = pkgs.lib.removePrefix (toString ../native + "/") (toString path);
            value = builtins.hashFile "sha256" path;
          })
          (
            builtins.filter (path: pkgs.lib.hasSuffix ".py" (toString path)) (
              pkgs.lib.filesystem.listFilesRecursive ../native
            )
          )
      );
      providers = pkgs.lib.genAttrs [ "scope.nix" "environment.nix" ] (
        name: builtins.hashFile "sha256" (./. + ("/" + name))
      );
    }
  );
})
