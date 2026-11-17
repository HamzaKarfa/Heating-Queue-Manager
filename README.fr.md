# Resource Queue Manager — Guide en français

[Documentation complète en anglais](README.md) · [Architecture v1](docs/V1_ARCHITECTURE.md) · [Migration v0.4 → v1](docs/MIGRATION_v0.4_to_v1.md) · [Notes de version](docs/releases/v1.0.0.md)

**Resource Queue Manager** permet de gérer plusieurs files de ressources indépendantes dans Home Assistant, avec les stratégies **FIFO, LIFO et FIFO avec priorité**, une capacité configurable et des réservations persistantes. Les files coordonnent les autorisations ; les automatisations restent responsables de la commande des appareils.

> **Version 1.0.0 en préparation.** Ce guide concerne la branche `feat/v1-multi-queue-strategies`. La v1 n'est **pas encore publiée** sur Marketplace : la branche principale conserve la version stable v0.4 jusqu'à validation et publication explicite.

> **Sécurité :** l'intégration ne commande jamais directement les relais. Tes automatisations décident d'allumer et d'éteindre les appareils après réservation. Ce logiciel n'est ni un délesteur électrique certifié, ni un système de protection thermique ; les sécurités matérielles restent indispensables.

## Les nouveautés de la v1

Chaque instance possède son **nom**, sa **capacité** (entre 1 et 50 réservations simultanées), ses **entités supervisées**, son **algorithme**, ses capteurs et sa sauvegarde. Il est possible de créer plusieurs gestionnaires depuis **Paramètres → Appareils et services → Ajouter une intégration**.

| Stratégie | Comportement |
| --- | --- |
| **FIFO** | Premier arrivé, premier servi |
| **LIFO** | Dernier arrivé parmi les demandes en attente, premier servi |
| **FIFO avec priorité** | Niveau de priorité (1 à 10), puis ordre d'arrivée en cas d'égalité |

Pour **FIFO avec priorité**, choisir le sens des priorités : `highest_first` (10 avant 1) ou `lowest_first` (1 avant 10).

Les stratégies n'interrompent **jamais** une réservation déjà active. Une priorité faible peut rester en attente indéfiniment si les demandes prioritaires s'enchaînent : il n'existe pas encore de mécanisme de vieillissement.

## Installation et tests

**Prérequis : Home Assistant 2026.11.0 ou version ultérieure.**

Pour la version stable, rechercher **Resource Queue Manager** dans **Marketplace**, ou utiliser le lien `https://github.com/HamzaKarfa/Resource-Queue-Manager`. Le Marketplace installe la version actuellement publiée, et **pas** les modifications de la PR en cours.

Pour tester la v1 **avant sa publication** :

1. Faire une sauvegarde complète ou, de préférence, utiliser un Home Assistant de test.
2. Récupérer le dossier complet `custom_components/resource_queue_manager` depuis la [branche v1](https://github.com/HamzaKarfa/Resource-Queue-Manager/tree/feat/v1-multi-queue-strategies/custom_components/resource_queue_manager).
3. Le copier dans le répertoire `config/custom_components/` du Home Assistant de test, sans mélanger les fichiers de versions différentes.
4. Redémarrer Home Assistant puis ajouter l'intégration **Resource Queue Manager**.
5. Configurer un nom, une stratégie, une capacité et quelques entités `light` ou `switch` **sans risque**, par exemple une lampe de test.
6. Contrôler les états physiques et les capteurs avant de reprendre la file.

Une même entité ne peut pas être supervisée par deux files. Il n'existe **aucune limite globale de puissance** entre les différentes files.

## Appels d'actions

Chaque action doit cibler l'entrée concernée avec `config_entry_id` lorsqu'au moins deux gestionnaires sont configurés. Il s'agit de l'**identifiant de l'entrée Home Assistant**, proposé dans le sélecteur des outils de développement, pas de son nom.

### Reprendre une file après le démarrage

À chaque redémarrage, les gestionnaires reviennent en mode `paused`. Il faut contrôler les entités supervisées puis reprendre **chaque** file :

```yaml
action: resource_queue_manager.resume
data:
  config_entry_id: "ID_DE_L_ENTREE"
```

### Demander une place avec priorité

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "ID_DE_L_ENTREE"
  resource_id: chambre_1
  entity_id: switch.relais_chambre_test
  strategy_data:
    priority: 8
```

Pour FIFO et LIFO, **ne pas ajouter `strategy_data`** ; leurs providers n'acceptent aucune métadonnée. Pour FIFO avec priorité, le champ `priority` est obligatoire pour une nouvelle demande.

Une demande peut être accordée immédiatement ou placée en attente. **L'automatisation doit vérifier l'octroi de la réservation** via le capteur `active` de la bonne file (ou l'événement `resource_queue_manager_slot_granted`) avant d'allumer l'appareil.

### Libérer une place

Après extinction, **attendre la confirmation de l'état `off` dans Home Assistant** :

```yaml
action: resource_queue_manager.release
data:
  config_entry_id: "ID_DE_L_ENTREE"
  resource_id: chambre_1
```

L'action `resource_queue_manager.cancel` permet de retirer une demande en attente ou une réservation active dont l'appareil est bien éteint.

## Capteurs et récupération

Chaque gestionnaire crée quatre capteurs : **active**, **waiting**, **available** et **status**. Leurs attributs présentent l'ordre des ressources, la stratégie, l'identifiant de configuration et les éventuels problèmes de récupération (`recovery_issues`).

Les installations provenant de la v0.4 conservent les identifiants uniques de leurs capteurs d'origine ; les nouvelles files prennent le nom configuré. Vérifier les véritables identifiants dans Home Assistant avant d'écrire les automatisations.

Si `resume` échoue, une entité peut être absente, indisponible ou allumée sans réservation. **Ne jamais supprimer une sauvegarde de réservation pour contourner ce contrôle.**

## Migration v0.4 → v1

La migration conserve le domaine `resource_queue_manager`, les anciens noms d'actions et la file FIFO existante. Les anciennes sauvegardes restent lisibles et l'ancien gestionnaire reste configuré en FIFO.

**Point important : dès la création d'une deuxième entrée, les actions sans `config_entry_id` échouent volontairement.** Il faut donc ajouter cet identifiant aux automatisations d'origine **avant** de créer la deuxième file.

Une stratégie ou ses paramètres ne peuvent être modifiés que lorsque la file est entièrement vide. Tout rechargement laisse la file en pause jusqu'à une nouvelle reprise explicite.

Consulter impérativement le [guide complet de migration, avec procédure de retour arrière](docs/MIGRATION_v0.4_to_v1.md) avant de faire des essais sur une installation existante.

## Développement et publication

Les tests Python, les tests d'intégration Home Assistant, HACS et hassfest sont exécutés par GitHub Actions. La version `1.0.0` est préparée dans le manifeste de la branche, **sans créer de release publique**.

La publication est manuelle, réservée à la branche `main` après validation : consulter [DEVELOPMENT.md](docs/DEVELOPMENT.md). La PR reste en brouillon jusqu'aux tests sur une installation Home Assistant de test.

Licence : [MIT](LICENSE).
