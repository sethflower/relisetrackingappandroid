{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  buildInputs = [
    pkgs.flutter
    pkgs.git
    pkgs.zip
    pkgs.gh
  ];
}
