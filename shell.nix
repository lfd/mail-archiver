{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  nativeBuildInputs = with pkgs.buildPackages; [
    git
    python313
    python313Packages.dateparser
    python313Packages.pygit2
    python313Packages.tqdm
  ];
}
