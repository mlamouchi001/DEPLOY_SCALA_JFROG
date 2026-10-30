# DEPLOY_SCALA_JFROG

Playbooks AWX de déploiement des projets Scala / Spark sur les edges. Ils sont lancés par le workflow réutilisable `deploy_awx_jfrog.yml` de `reusable-github-actions`.

Le playbook télécharge le jar et le bundle zip depuis JFrog, les installe sur les edges et les copie sur HDFS. Il dépose aussi, si besoin, le fichier de configuration Vault (AppRole).

Le projet AWX et les job templates n'ont pas à changer :
- les playbooks gardent leurs noms (`deploy.yml`, `deploy_vault.yml`) ;
- les hôtes restent `edges,edge_lucid` ;
- les extra vars sont les mêmes ;
- les nouvelles variables sont facultatives.

## Contenu

| Fichier | Rôle |
|---|---|
| `deploy.yml` | Playbook standard. Il dépose `vault.conf` si le workflow l'envoie. |
| `deploy_vault.yml` | Variante Vault historique : bundle et HDFS toujours traités, fichier Vault à son emplacement historique. |
| `tasks/deploy_scala.yml` | Étapes communes aux deux playbooks. |
| `tasks/download.yml` | Téléchargement JFrog : présence, empreinte SHA-256, nouvelles tentatives, erreurs lisibles. |
| `tasks/vault.yml` | Construction et dépôt du fichier Vault (droits 600). |
| `group_vars/global.yml`, `group_vars/<env>/<env>.yml` | Chemins, URL JFrog et réglages de téléchargement par environnement. |
| `files/vault.conf` | Modèle du fichier Vault du mode `approle_id` / `approle_secret`. |
| `library/` | Modules `hdfs_copy`, `hdfs_file`, `spark_app` et `maven_artifact_fixed`. |

## Arborescence installée sur l'edge

```
<path_principal_deploy>/<irt_trigram>/<env>/<path_source>/     ex. /DATA/applications_01/bsy_a2918/dev/scala
├── bin/<jar_name>.jar      fat jar téléchargé depuis JFrog
├── sh/*.sh                 scripts du bundle zip
├── conf/*.conf             configuration du bundle (deploy_config_file)
├── conf/vault.conf         fichier Vault (deploy.yml), droits 600
└── tmp/deploy_XXXX/        dossier de travail, supprimé à la fin du déploiement
```

Sur HDFS, le déploiement écrit dans `/<env>/<app_config>/<irt_trigram>/{bin,sh,conf}`.

## Étapes

1. **Contrôle des extra vars.** Le déploiement s'arrête avant toute modification du serveur si :
   - `env` n'est pas une valeur attendue ;
   - un paramètre obligatoire manque ;
   - un nom contient `/` ou `..`.
2. **Téléchargement depuis JFrog** du jar `<project_name>-<project_version>.jar`, et du zip si le bundle est traité.
   - Le playbook vérifie d'abord la présence du fichier (requête HEAD).
   - Il contrôle l'empreinte SHA-256 publiée par JFrog (en-tête `X-Checksum-Sha256`). Un fichier tronqué ou altéré est refusé.
   - Il fait jusqu'à `download_retries` tentatives.
   - En cas d'échec, le message est lisible et sans secret : par exemple 404 pour une version ou un dépôt erroné, 401/403 pour un jeton invalide.
3. **Jar** : installé dans `bin/`, puis copié sur HDFS si `deploy_hdfs`.
4. **Scripts** `*.sh` du bundle : installés dans `sh/` en 0755, puis copiés sur HDFS si `deploy_hdfs`.
5. **Configuration** (`deploy_config_file: true`) :
   - `application_conf: all` prend tous les `*.conf` du bundle ; sinon, seulement le fichier nommé, et le déploiement échoue s'il est absent ;
   - les fichiers sont installés dans `conf/` et copiés sur HDFS.
6. **Fichier Vault** (voir ci-dessous).
7. **Fin** : un résumé est affiché, et le dossier de travail est supprimé, même en cas d'échec.

## Fichier Vault

Le fichier est écrit en 600. Ni son contenu, ni le jeton JFrog, ni l'AppRole n'apparaissent dans la sortie du job AWX, même en `-vvv`.

Il y a deux sources possibles. La première trouvée l'emporte :

| Extra vars | Contenu |
|---|---|
| `vault_conf_b64` | Fichier complet construit par le workflow GitHub Actions (`vault_enabled: true`) à partir des secrets du dépôt. |
| `approle_id` + `approle_secret` | Le modèle `files/<file_conf>`, dont `#{approle_id}` et `#{approle_secret}` sont remplacés. |

Son emplacement dépend du playbook :

| Playbook | Emplacement |
|---|---|
| `deploy.yml` | `<application>/<vault_conf_path, défaut conf>/<vault_conf_name, défaut file_conf ou vault.conf>` |
| `deploy_vault.yml` | `<path_principal_deploy>/<irt_trigram>/<path_conf>/<file_conf>`, comme avant |

Le déploiement échoue si le fichier ne contient pas `roleId` et `secretId`, ou s'il reste des valeurs non remplacées (`#{approle_...}`, `A_RENSEIGNER`).

## Extra vars

**Envoyées par le workflow GitHub Actions** (inchangées) :
- `env`, `irt_trigram`, `app_config`, `path_source` ;
- `project_group_id`, `path_group_id`, `project_name`, `project_version`, `app_version`, `jar_name` ;
- `repo_jfrog_prj`, `jf_access_token` ;
- `deploy_config_file`, `application_conf`, `deploy_hdfs`, `only_jar` ;
- `file_conf`, `path_conf`, `approle_id`, `approle_secret`.

**Facultatives, nouvelles** :
- `vault_conf_b64`, `vault_conf_name`, `vault_conf_path` ;
- `vault_only` : `true` pour déposer seulement le fichier Vault, sans téléchargement, ni jar, ni HDFS, ni jeton JFrog. Les projets dont le dépôt générique ne gère pas Vault l'utilisent : leur CD relance le même job template avec `vault_conf_b64` ;
- `deploy_bundle` : `true` ou `false`, prioritaire sur `only_jar` ;
- `download_retries`, `download_delay`, `download_timeout`.

**Variables d'inventaire AWX** (inchangées) :
- `keytab_path` et `keytab_principal`, pour les copies HDFS ;
- `owner`, `group` et `mode`, facultatives.

**Kerberos** (`tasks/kerberos.yml`). Avant les copies HDFS, le playbook vérifie que le keytab existe et qu'il est lisible, puis lit ses principaux avec `klist -k`.
- Si `keytab_principal` n'y figure pas, le principal du keytab est utilisé à sa place, et un avertissement est affiché. C'est le cas, par exemple, quand on fournit `xxx.applicatif.keytab@REALM`, c'est-à-dire le nom du fichier au lieu du principal.
- Le déploiement fonctionne donc sans corriger l'inventaire AWX, mais il vaut mieux le corriger à l'occasion.

Points à connaître :
- **`only_jar` a un sens inversé.** Dans `deploy.yml`, le bundle zip (scripts et configuration) n'est traité que si `only_jar == "true"`. C'est la valeur par défaut du workflow. Le comportement est conservé pour ne casser aucun projet. Pour l'exprimer clairement, utilisez `deploy_bundle`.
- **Configuration sur HDFS.** Elle est copiée dès que `deploy_config_file` vaut `true`, comme avant avec `application_conf: all`.

## Corrections par rapport à la version précédente

- **Mauvais fichiers copiés.** La copie HDFS de la configuration copiait les scripts shell (boucle sur `scripts_files`). Elle copie maintenant les fichiers de configuration.
- **Droits du fichier Vault.** Il était créé avec les droits par défaut, donc lisible par tous. Il est désormais en 600.
- **Secrets dans les journaux.** Le jeton JFrog et l'AppRole apparaissaient en clair dans les événements du job AWX (arguments des tâches `get_url` et `replace`). Ces tâches sont maintenant en `no_log`.
- **`tmp/` jamais vidé.** Les anciens jars et zips s'y accumulaient, et la recherche récursive de `*.jar`/`*.conf` pouvait reprendre des fichiers d'un déploiement précédent. Chaque déploiement a maintenant son propre dossier de travail, supprimé à la fin.
- **Téléchargements.** Ils se faisaient sans contrôle d'intégrité ni nouvelle tentative, et les erreurs étaient peu lisibles.
- **Auto-références dans `group_vars/global.yml`.** Les lignes du type `jar_name: "{{ jar_name }}"` provoquaient une erreur de récursion si l'extra var manquait.
- **Fichier de configuration demandé mais absent du bundle.** Le déploiement réussissait quand même ; il échoue maintenant avec un message clair.
- **Nettoyage.** Les tâches dupliquées, les `debug` des structures complètes et la syntaxe dépréciée `copy: no` sont supprimés.

## Recommandation AWX

AWX affiche les extra vars de lancement (dont `jf_access_token` et l'AppRole) dans le détail du job, pour les utilisateurs qui ont accès au template. Le playbook ne peut pas l'empêcher.

La solution passe par AWX lui-même : un type d'identifiant (credential type) ou un survey en mode mot de passe. Cela demande de modifier le template, ce qui est volontairement hors du périmètre de ce dépôt.
