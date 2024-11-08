{pkgs}: {
  deps = [
    pkgs.libev
    pkgs.redis
    pkgs.postgresql
    pkgs.openssl
  ];
}
