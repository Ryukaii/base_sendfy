{pkgs}: {
  deps = [
    pkgs.coreutils
    pkgs.redis
    pkgs.postgresql
    pkgs.openssl
  ];
}
