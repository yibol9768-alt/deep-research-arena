#!/usr/bin/env bash
eng=$(timeout 15 docker --context desktop-linux version --format '{{.Server.Version}}' 2>/dev/null)
if [ -z "$eng" ]; then echo "engine=booting"; exit 0; fi
shop=$(timeout 20 docker --context desktop-linux images --format '{{.Repository}}' 2>/dev/null | grep -cE 'shopping_final|postmill')
echo "engine=$eng images_shop_forum=$shop"
