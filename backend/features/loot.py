import logging
from features.base import Feature

logger = logging.getLogger(__name__)


class MassDisenchant(Feature):
    key = "mass_disenchant"
    title = "Loot & Crafting"
    category = "Customization"

    def get_status(self) -> dict:
        champion_shards = 0
        skin_shards = 0
        key_fragments = 0
        chests_count = 0
        total_shards = 0

        if self.lcu.is_league_connected():
            try:
                res = self.lcu.lcu_request("GET", "/lol-loot/v1/player-loot")
                if res.status_code == 200:
                    loot_list = res.json()
                    for item in loot_list:
                        item_type = item.get("type", "")
                        # .get(..., "") only covers a missing key - the LCU
                        # can also return "lootId": null, which the default
                        # doesn't catch and which crashes .startswith()/.lower().
                        loot_id = item.get("lootId") or ""
                        count = int(item.get("count", 1))

                        if item_type in ("CHAMPION_RENTAL", "CHAMPION"):
                            champion_shards += count
                            total_shards += count
                        elif item_type in ("SKIN_RENTAL", "SKIN"):
                            skin_shards += count
                            total_shards += count
                        elif item_type in ("WARD_SKIN_RENTAL", "STATSTONE_SHARD", "EMOTE"):
                            total_shards += count
                        elif loot_id == "MATERIAL_key_fragment":
                            key_fragments += count
                        elif item_type == "CHEST" or loot_id.startswith("CHEST_"):
                            chests_count += count
            except Exception:
                logger.exception("MassDisenchant.get_status failed")

        return {
            "key": self.key,
            "champion_shards": champion_shards,
            "skin_shards": skin_shards,
            "key_fragments": key_fragments,
            "chests": chests_count,
            "total_shards": total_shards,
        }

    def forge_keys(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        res = self.lcu.lcu_request("GET", "/lol-loot/v1/player-loot")
        if res.status_code != 200:
            raise RuntimeError(f"Could not fetch player loot (HTTP {res.status_code})")

        loot_list = res.json()
        forged = 0

        for item in loot_list:
            if item.get("lootId") == "MATERIAL_key_fragment":
                count = int(item.get("count", 0))
                keys_to_forge = count // 3
                if keys_to_forge > 0:
                    craft_res = self.lcu.lcu_request(
                        "POST",
                        f"/lol-loot/v1/recipes/MATERIAL_key_fragment_forge/craft?repeat={keys_to_forge}",
                        ["MATERIAL_key_fragment"],
                    )
                    if craft_res.status_code in (200, 201, 204):
                        forged += keys_to_forge

        self.on_event("success", f"Forged {forged} key(s)")
        return {"forged_keys": forged}

    def open_chests(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        res = self.lcu.lcu_request("GET", "/lol-loot/v1/player-loot")
        if res.status_code != 200:
            raise RuntimeError(f"Could not fetch player loot (HTTP {res.status_code})")

        loot_list = res.json()
        opened = 0

        # Check key count
        keys_available = 0
        for item in loot_list:
            if item.get("lootId") == "MATERIAL_key":
                keys_available = int(item.get("count", 0))

        for item in loot_list:
            loot_id = item.get("lootId") or ""
            item_type = item.get("type", "")
            count = int(item.get("count", 0))

            if item_type == "CHEST" or loot_id.startswith("CHEST_"):
                # Check if it requires a key (generic hextech/masterwork)
                if "generic" in loot_id.lower() or "masterwork" in loot_id.lower() or "champion_mastery" in loot_id.lower():
                    to_open = min(count, keys_available)
                    if to_open > 0:
                        recipe = f"{loot_id}_OPEN"
                        craft_res = self.lcu.lcu_request(
                            "POST",
                            f"/lol-loot/v1/recipes/{recipe}/craft?repeat={to_open}",
                            [loot_id, "MATERIAL_key"],
                        )
                        if craft_res.status_code in (200, 201, 204):
                            opened += to_open
                            keys_available -= to_open
                else:
                    # Keyless capsules/orbs
                    recipe = f"{loot_id}_OPEN"
                    craft_res = self.lcu.lcu_request(
                        "POST",
                        f"/lol-loot/v1/recipes/{recipe}/craft?repeat={count}",
                        [loot_id],
                    )
                    if craft_res.status_code in (200, 201, 204):
                        opened += count

        self.on_event("success", f"Opened {opened} container(s)")
        return {"opened": opened}

    def disenchant_champions(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        res = self.lcu.lcu_request("GET", "/lol-loot/v1/player-loot")
        if res.status_code != 200:
            raise RuntimeError(f"Could not fetch player loot (HTTP {res.status_code})")

        loot_list = res.json()
        disenchanted_count = 0

        for item in loot_list:
            item_type = item.get("type", "")
            loot_id = item.get("lootId", "")
            count = int(item.get("count", 1))

            if item_type == "CHAMPION_RENTAL":
                recipe = "CHAMPION_RENTAL_disenchant"
            elif item_type == "CHAMPION":
                recipe = "CHAMPION_disenchant"
            else:
                continue

            craft_res = self.lcu.lcu_request(
                "POST",
                f"/lol-loot/v1/recipes/{recipe}/craft?repeat={count}",
                [loot_id],
            )
            if craft_res.status_code in (200, 201, 204):
                disenchanted_count += count

        self.on_event("success", f"Disenchanted {disenchanted_count} champion shard(s)")
        return {"disenchanted": disenchanted_count}

    def disenchant_all(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        res = self.lcu.lcu_request("GET", "/lol-loot/v1/player-loot")
        if res.status_code != 200:
            raise RuntimeError(f"Could not fetch player loot (HTTP {res.status_code})")

        loot_list = res.json()
        disenchanted_count = 0

        # Deliberately excludes SKIN/SKIN_RENTAL: skin shards are the one kind
        # of loot users do not want destroyed by a bulk action. The confirmation
        # dialog in the UI lists exactly these categories.
        type_to_recipe = {
            "CHAMPION_RENTAL": "CHAMPION_RENTAL_disenchant",
            "CHAMPION": "CHAMPION_disenchant",
            "WARD_SKIN_RENTAL": "WARD_SKIN_RENTAL_disenchant",
            "STATSTONE_SHARD": "STATSTONE_SHARD_disenchant",
        }

        for item in loot_list:
            item_type = item.get("type", "")
            loot_id = item.get("lootId", "")
            count = int(item.get("count", 1))

            recipe = type_to_recipe.get(item_type)
            if not recipe:
                continue

            craft_res = self.lcu.lcu_request(
                "POST",
                f"/lol-loot/v1/recipes/{recipe}/craft?repeat={count}",
                [loot_id],
            )
            if craft_res.status_code in (200, 201, 204):
                disenchanted_count += count

        self.on_event("success", f"Disenchanted {disenchanted_count} loot item(s)")
        return {"disenchanted": disenchanted_count}
