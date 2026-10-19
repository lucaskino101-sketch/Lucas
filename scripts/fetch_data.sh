#!/usr/bin/env bash
# Fetch 1-minute Oanda mid-price data (2005-01 .. 2020-05) from the public
# FutureSharks/financial-data repository, only for the instruments we use.
set -euo pipefail
DEST="${1:-/home/user/futuresharks/financial-data}"
if [ ! -d "$DEST/.git" ]; then
  GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/FutureSharks/financial-data "$DEST"
fi
git -C "$DEST" sparse-checkout set --no-cone \
  'pyfinancialdata/data/currencies/oanda/NAS100_USD/' \
  'pyfinancialdata/data/currencies/oanda/SPX500_USD/' \
  'pyfinancialdata/data/currencies/oanda/EUR_USD/' \
  'pyfinancialdata/data/currencies/oanda/GBP_USD/' \
  'pyfinancialdata/data/currencies/oanda/XAU_USD/'
echo "raw data ready under $DEST/pyfinancialdata/data/currencies/oanda"
