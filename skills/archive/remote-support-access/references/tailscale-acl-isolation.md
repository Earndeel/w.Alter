# ACL Tailscale — Isolation des clients W.Alter

À appliquer dans **admin.tailscale.com → Access Controls** AVANT d'envoyer le package.

## ACL minimale

```jsonc
{
    // ... vos ACLs existantes ...

    "acls": [
        // ... vos règles existantes ...

        // W.Alter → clients : SSH + VNC uniquement
        {
            "action": "accept",
            "src":    ["tag:w-alter"],
            "dst":    ["tag:w-alter-clients:*"],
            "proto":  ["tcp"],
            "dstPort": [22, 5900]
        }
        // AUCUNE règle dans l'autre sens — les clients ne peuvent rien initier
    ],

    "tagOwners": {
        "tag:w-alter":         ["autogroup:admin"],
        "tag:w-alter-clients": ["autogroup:admin"]
    }
}
```

## Effet

- `tag:w-alter` → peut SSH + VNC vers les clients
- `tag:w-alter-clients` → ne peut RIEN initier (même pas ping)
- Même si le Mac ami est compromis, il ne peut pas scanner le tailnet

## Vérification

Après application, depuis w-alter :
```bash
# Vérifier que le client est isolé
tailscale status | grep "ami-"
# Le client doit apparaître avec le tag:w-alter-clients

# Vérifier qu'il est joignable
ssh -i ~/.ssh/id_ed25519 <ip-tailscale> "echo OK"
```
