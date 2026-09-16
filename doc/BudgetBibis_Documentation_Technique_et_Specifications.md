# BudgetBibis — Documentation technique et spécifications

**Version 1.0 — 16 septembre 2026**

> Statut : documentation de référence de la version courante analysée.

## 1. Objet du document

Ce document décrit les spécifications fonctionnelles, les règles de gestion, l’architecture technique, le modèle de données, l’installation, l’exploitation et la stratégie de test de l’application **BudgetBibis**.

Il correspond à la version du code comprenant la correction du filtre **« Uniquement non catégorisées »** et la sécurisation de la sélection d’une transaction qui disparaît du résultat filtré après sa catégorisation.

### 1.1 Public visé

- utilisateur et propriétaire de BudgetBibis ;
- mainteneur Python/Streamlit ;
- intervenant Talend chargé d’alimenter la base SQLite ;
- personne chargée de tester ou de faire évoluer l’application.

### 1.2 Sources analysées

- `app.py` : interface Streamlit et orchestration ;
- `db.py` : accès SQLite, validations et écritures métier ;
- `analytics.py` : calculs analytiques et fonctions de filtrage ;
- `tests/test_db.py` et `tests/test_filters.py` : tests automatisés ;
- `requirements.txt`, `README.md` et `MISE_A_JOUR.txt`.

## 2. Présentation générale

BudgetBibis est une application locale de gestion et d’analyse budgétaire. Les relevés bancaires sont préparés et mappés en amont avec Talend, puis chargés dans une base SQLite. L’application fournit une interface ponctuelle et simple pour consulter, analyser et enrichir ces données.

### 2.1 Objectifs

1. centraliser les transactions bancaires déjà normalisées par Talend ;
2. visualiser les entrées, sorties, soldes et répartitions par catégorie ;
3. corriger manuellement une catégorie, une sous-catégorie, une date effective, un type de mouvement ou un commentaire ;
4. administrer les référentiels de catégorisation ;
5. suivre les mensualités, amortissements, emprunts et montants à transférer ;
6. conserver toutes les modifications dans la base SQLite locale.

### 2.2 Périmètre

**Inclus :** consultation, filtres, statistiques, graphiques, édition des transactions, référentiels, mensualités, suivi, emprunts et amortissements.

**Hors périmètre actuel :** authentification multi-utilisateur, serveur centralisé, synchronisation bancaire directe, exécution de Talend depuis l’interface, gestion de plusieurs devises, API publique et application mobile native.

## 3. Architecture fonctionnelle

L’application est organisée en sept onglets :

| Onglet | Finalité |
|---|---|
| Tableau de bord | Indicateurs, tendances mensuelles, dépenses et revenus par catégorie, soldes et prévisionnel |
| Transactions | Consultation des opérations filtrées et modification d’une transaction |
| Mensualités | Administration de `prelevementMensualise` |
| Suivi | Calcul du transfert vers Trade Republic, minimum à conserver, surplus et solde précédent |
| Emprunts | Consultation des emprunts actifs et modification du capital restant |
| Amortissements | Gestion des réserves, mensualités globales, contributions et restitutions |
| Référentiels et règles | Gestion des catégories, sous-catégories et règles de libellés |

Les filtres de la barre latérale s’appliquent au tableau de bord et à la liste des transactions : période, banque, compte, catégorie effective, uniquement non catégorisées et recherche textuelle dans les libellés.

## 4. Spécifications fonctionnelles

### 4.1 Tableau de bord

| ID | Exigence |
|---|---|
| RF-TDB-01 | Afficher les entrées, sorties, solde net, nombre d’opérations comptabilisées et nombre de transactions non catégorisées. |
| RF-TDB-02 | Exclure des statistiques et graphiques toute transaction dont la catégorie effective possède `exclu = 1`. |
| RF-TDB-03 | Conserver les transactions exclues visibles dans l’onglet Transactions. |
| RF-TDB-04 | Afficher les entrées et sorties agrégées par mois. |
| RF-TDB-05 | Pour le mois sélectionné, consolider chaque catégorie par son solde net `revenus − dépenses`. |
| RF-TDB-06 | Afficher une catégorie uniquement dans Revenus si son solde net est positif, uniquement dans Dépenses s’il est négatif, et nulle part s’il vaut zéro. |
| RF-TDB-07 | Afficher toutes les lignes des tableaux mensuels sans défilement interne. |
| RF-TDB-08 | Afficher le solde du mois en vert s’il est positif, rouge s’il est négatif, gris s’il est nul. |
| RF-TDB-09 | Afficher un anneau des dépenses avec les 7 catégories principales, des pictogrammes et un classement complet. |
| RF-TDB-10 | Afficher le solde du mois précédent, le solde total et le solde total prévisionnel. |
| RF-TDB-11 | Afficher le reste à prélever du mois sans l’intégrer au solde mensuel. |

### 4.2 Transactions et filtres

| ID | Exigence |
|---|---|
| RF-TRX-01 | Afficher toutes les transactions répondant aux filtres, y compris les catégories exclues des statistiques. |
| RF-TRX-02 | La catégorie effective est la catégorie forcée si elle existe, sinon la catégorie calculée. |
| RF-TRX-03 | La sous-catégorie effective suit la même règle de priorité. |
| RF-TRX-04 | Le filtre « Uniquement non catégorisées » retient une transaction seulement si la catégorie calculée **et** la catégorie forcée sont absentes, vides ou composées uniquement d’espaces. |
| RF-TRX-05 | Le compteur « Non catégorisées » applique exactement la même définition. |
| RF-TRX-06 | La sélection d’une ligne pré-sélectionne la transaction dans le formulaire. |
| RF-TRX-07 | Si une modification fait disparaître la ligne du filtre actif, une ancienne position de sélection ne doit provoquer aucune erreur ; elle est ignorée et la première ligne restante devient sélectionnable. |
| RF-TRX-08 | Modifier la catégorie forcée, la sous-catégorie forcée, le type de mouvement, le commentaire et la date effective forcée. |
| RF-TRX-09 | Une sous-catégorie forcée doit appartenir à la catégorie forcée choisie et être active. |
| RF-TRX-10 | Sans catégorie forcée, le sélecteur de sous-catégorie est désactivé. |
| RF-TRX-11 | Remettre la date forcée à `NULL` restaure la date bancaire originale comme date effective. |
| RF-TRX-12 | Les catégories et sous-catégories proposées sont triées alphabétiquement. |

### 4.3 Référentiels et règles

| ID | Exigence |
|---|---|
| RF-REF-01 | Créer une catégorie avec nom, priorité, statut actif et statut d’exclusion. |
| RF-REF-02 | Refuser deux catégories portant le même nom sans tenir compte de la casse. |
| RF-REF-03 | Créer une sous-catégorie rattachée à une catégorie. |
| RF-REF-04 | Refuser les doublons de sous-catégorie dans une même catégorie. |
| RF-REF-05 | Renommer catégories et sous-catégories sans modifier leurs identifiants ni casser les relations. |
| RF-REF-06 | Créer une règle de libellé associée à une sous-catégorie. |
| RF-REF-07 | La suppression d’une règle conserve les transactions et met leur `id_libelle_transforme` à `NULL`, après confirmation. |

### 4.4 Mensualités

| ID | Exigence |
|---|---|
| RF-MEN-01 | Lister, créer, modifier et supprimer les lignes de `prelevementMensualise`. |
| RF-MEN-02 | Tous les champs sont modifiables sauf l’identifiant. |
| RF-MEN-03 | Le jour de prélèvement est compris entre 1 et 31. |
| RF-MEN-04 | Les montants ne peuvent pas être négatifs. |
| RF-MEN-05 | La sous-catégorie choisie doit appartenir à la catégorie choisie. |
| RF-MEN-06 | Toute suppression nécessite une confirmation explicite. |

### 4.5 Suivi

| ID | Exigence |
|---|---|
| RF-SUI-01 | Calculer les mensualités Trade Republic par comparaison insensible à la casse et aux espaces périphériques. |
| RF-SUI-02 | Calculer la somme des mensualités de tous les amortissements. |
| RF-SUI-03 | Enregistrer un surplus souhaité persistant et positif ou nul. |
| RF-SUI-04 | Calculer le transfert mensuel : `mensualités Trade Republic + mensualités des amortissements + surplus`. |
| RF-SUI-05 | Calculer le minimum Trade Republic : `mensualités Trade Republic + soldes des amortissements + solde amortissementManuel`. |
| RF-SUI-06 | Enregistrer un solde du mois précédent positif, nul ou négatif. |
| RF-SUI-07 | Calculer le reste à prélever par banque et compte pour les jours supérieurs ou égaux au jour courant. |
| RF-SUI-08 | Le reste à prélever n’affecte ni le transfert mensuel ni le solde mensuel ; il intervient seulement dans le prévisionnel. |

### 4.6 Emprunts

| ID | Exigence |
|---|---|
| RF-EMP-01 | Afficher uniquement les emprunts dont `restantARembourse > 0`. |
| RF-EMP-02 | Autoriser uniquement la modification du restant à rembourser. |
| RF-EMP-03 | Refuser un restant négatif ou supérieur au montant emprunté. |
| RF-EMP-04 | Calculer l’avancement, borné entre 0 % et 100 %, par `(montantEmprunte − restantARembourse) / montantEmprunte × 100`. |
| RF-EMP-05 | Un emprunt dont le restant atteint zéro disparaît de la liste active. |

### 4.7 Amortissements

| ID | Exigence |
|---|---|
| RF-AMO-01 | Consulter, créer et modifier un amortissement. |
| RF-AMO-02 | Associer une catégorie et une sous-catégorie cohérentes à chaque amortissement. |
| RF-AMO-03 | Calculer l’avancement financier par `solde / objectif × 100`. |
| RF-AMO-04 | Colorer l’avancement financier en vert uniquement lorsqu’il vaut exactement 100 %. |
| RF-AMO-05 | Calculer la progression des mensualités par `((mois restant × mensualité ajustée) + solde) / objectif × 100`. |
| RF-AMO-06 | Colorer cette progression en rouge sous 70 %, orange de 70 % à 90 % inclus, vert au-dessus de 90 %. |
| RF-AMO-07 | Fixer `mensualite_ajustee` à zéro lorsque l’avancement financier atteint ou dépasse 100 %, sinon à la mensualité normale. |
| RF-AMO-08 | Préremplir la mensualité globale avec la somme des mensualités normales augmentée du surplus souhaité. |
| RF-AMO-09 | Refuser un montant global inférieur à la somme des mensualités normales. |
| RF-AMO-10 | Répartir le montant de base au centime, proportionnellement aux mensualités ajustées positives. |
| RF-AMO-11 | Ne créer aucune transaction à 0 €. |
| RF-AMO-12 | Utiliser l’association propre de chaque amortissement ; utiliser l’association globale comme repli. |
| RF-AMO-13 | Créer pour le surplus une transaction négative « Épargne » et augmenter `comptes.amortissementManuel` du même montant. |
| RF-AMO-14 | Garantir que la somme des transactions créées est exactement l’opposé du montant global saisi. |
| RF-AMO-15 | Une restitution crée une transaction positive et diminue atomiquement le solde de l’amortissement. |
| RF-AMO-16 | Interdire une restitution supérieure au solde disponible. |
| RF-AMO-17 | Le solde `amortissementManuel` est modifiable indépendamment sans créer de transaction. |
| RF-AMO-18 | Une contribution globale ne modifie pas `dateDernierPaiment`. |

## 5. Règles de calcul et priorités

### 5.1 Date effective

```text
date_effective = dateTimestamp_forcee si renseignée, sinon dateTimestamp
```

Les horodatages SQLite sont interprétés en millisecondes UTC puis convertis dans le fuseau `Europe/Paris`. La date bancaire originale reste conservée.

### 5.2 Catégorie effective

```text
categorie_effective = categorie_forcee si renseignée, sinon categorie calculée
```

Pour l’exclusion des statistiques, le champ `exclu` de la catégorie forcée prévaut quand `id_categorie_forcee` est renseigné. Sinon, le champ de la catégorie calculée est utilisé.

### 5.3 Non catégorisé

```text
non_categorise = categorie absente/vide ET categorie_forcee absente/vide
```

La présence d’une seule des deux catégories suffit donc à considérer la transaction comme catégorisée.

### 5.4 Soldes

```text
solde_mois = somme des montants inclus du mois
solde_total = solde_mois + solde_mois_precedent
solde_total_previsionnel = solde_total - reste_a_prelever
```

Les dépenses stockées comme montants négatifs sont présentées en valeur positive dans les tableaux de dépenses.

### 5.5 Répartition au centime

La répartition des mensualités globales convertit le total en centimes, calcule les parts proportionnelles, attribue d’abord les parties entières puis distribue les centimes restants selon les plus grands restes. Cette méthode garantit l’égalité exacte entre le total saisi et la somme répartie.

## 6. Architecture technique

### 6.1 Pile logicielle

| Élément | Technologie / contrainte |
|---|---|
| Langage | Python 3.11 ou plus récent recommandé |
| Interface | Streamlit `>=1.40,<2` |
| Manipulation de données | pandas `>=2.2,<4` |
| Graphiques | Altair `>=5.0,<7` |
| Persistance | SQLite via le module standard `sqlite3` |
| Tests | `unittest` et `pandas.testing` |
| Alimentation | Talend, hors processus de l’application |

### 6.2 Découpage du code

| Fichier | Responsabilité |
|---|---|
| `app.py` | Construction de l’IHM, widgets, onglets, présentation et orchestration des appels métier |
| `db.py` | Connexion SQLite, requêtes, validations, transactions atomiques et conversions de dates |
| `analytics.py` | Exclusion statistique, définition des non-catégorisées, agrégats mensuels, soldes et sécurisation de sélection |
| `tests/test_db.py` | Tests d’intégrité, persistance, validations et calculs métier |
| `tests/test_filters.py` | Tests du filtre non catégorisé et des index de sélection périmés |
| `requirements.txt` | Bornes de versions des dépendances |

### 6.3 Flux principal

```text
Relevés bancaires → Talend → SQLite
                              ↓
                         db.py / sqlite3
                              ↓
                  pandas DataFrame / analytics.py
                              ↓
                       app.py / Streamlit
                              ↓
                navigateur local de l’utilisateur
```

### 6.4 Cache

Les chargements sont placés dans `st.cache_data`. La clé inclut le chemin, la taille et la date de modification nanoseconde du fichier SQLite. Après une écriture applicative, `clear_cache()` invalide les caches puis `st.rerun()` reconstruit l’écran.

### 6.5 Transactions SQLite

Le gestionnaire `connection()` :

- active `PRAGMA foreign_keys = ON` ;
- définit `PRAGMA busy_timeout = 10000` ;
- valide automatiquement en fin de traitement réussi ;
- annule la transaction en cas d’exception ;
- ferme toujours la connexion.

Les opérations associant création de transaction et modification de solde sont donc atomiques.

## 7. Modèle de données

Les noms ci-dessous proviennent des requêtes et contrôles présents dans le code. La base de production n’étant volontairement pas incluse dans les archives de mise à jour, cette section décrit les colonnes utilisées par l’application plutôt qu’un script DDL exhaustif.

### 7.1 Relations principales

```text
categories 1 ─── n sous_categorie 1 ─── n libelles
     │                   │                    │
     └────────────── transactions ────────────┘
     │                   │
     ├──────────── amortissement
     └──────────── prelevementMensualise

comptes ── ligne métier amortissementManuel
emprunts ── suivi indépendant
budgetbibis_settings ── paramètres clé/valeur
```

### 7.2 Tables et colonnes utilisées

#### `transactions`

| Colonne | Usage |
|---|---|
| `id` | Identifiant immuable |
| `dateTimestamp` | Horodatage bancaire original en millisecondes |
| `dateTimestamp_forcee` | Horodatage de remplacement facultatif |
| `compte`, `banque` | Origine de l’opération |
| `libelle_originale` | Libellé bancaire |
| `id_libelle_transforme` | Référence facultative vers `libelles` |
| `montant` | Montant signé : revenu positif, dépense négative |
| `id_categorie`, `id_sous_categorie` | Classement calculé/importé |
| `id_categorie_forcee`, `id_sous_categorie_forcee` | Classement manuel prioritaire |
| `type_mouvement`, `commentaire` | Enrichissements manuels |

#### `categories`

| Colonne | Usage |
|---|---|
| `id` | Identifiant |
| `priorite` | Ordre métier |
| `nom` | Libellé unique fonctionnel |
| `actif` | Disponibilité dans les formulaires |
| `exclu` | Exclusion des statistiques et graphiques (`0` ou `1`) |

#### `sous_categorie`

`id`, `nom`, `priorite`, `actif`, `id_categorie`. La relation parent/enfant est validée avant toute écriture applicative.

#### `libelles`

`id`, `motif`, `libelle_transforme`, `id_sous_categorie`. Une suppression dissocie les transactions avant de supprimer la règle.

#### `amortissement`

Colonnes utilisées : `id`, `nom`, `solde`, `Objectif`, `Ancien_objectif`, `AvancementPourcentage`, `Mois`, `Mois_restant`, `mensualite`, `mensualite_ajustee`, `date_cible`, `Progession_pourcentage`, `dateDernierPaiment`, `commentaire`, `id_categorie`, `id_sous_categorie`.

Les graphies historiques `Progession_pourcentage` et `dateDernierPaiment` sont maintenues pour compatibilité.

#### `prelevementMensualise`

`id`, `nom`, `mensualite`, `methode_paiment`, `jourDePrelevement`, `ancienneMensualite`, `id_categorie`, `id_sous_categorie`, `banque`, `compteBancaire`.

#### `emprunts`

`id`, `nom`, `montantEmprunte`, `restantARembourse`, `dateFinEmprunt`.

#### `comptes`

L’application exige exactement une ligne dont `nom = amortissementManuel`, recherchée sans tenir compte de la casse. Son `solde` représente la réserve manuelle.

#### `budgetbibis_settings`

```sql
CREATE TABLE IF NOT EXISTS budgetbibis_settings (
    cle TEXT PRIMARY KEY,
    valeur_reelle REAL NOT NULL
);
```

Clés actuellement utilisées :

- `surplus_mensualite_amortissement` ;
- `solde_mois_precedent`.

## 8. Interfaces et parcours utilisateurs

### 8.1 Catégoriser les opérations non catégorisées

1. activer **Uniquement non catégorisées** ;
2. ouvrir l’onglet Transactions ;
3. sélectionner une ligne ;
4. choisir une catégorie forcée ;
5. choisir éventuellement une sous-catégorie compatible ;
6. enregistrer ;
7. la transaction disparaît du filtre ; l’interface ignore la sélection devenue périmée et continue sans erreur.

### 8.2 Forcer ou restaurer une date

- décocher **Utiliser la date bancaire originale** pour saisir une date effective forcée ;
- recocher cette option pour enregistrer `dateTimestamp_forcee = NULL` ;
- la date bancaire n’est jamais écrasée.

### 8.3 Enregistrer une mensualité globale d’amortissements

1. contrôler les associations de chaque amortissement ;
2. saisir le montant global, au moins égal au total des mensualités normales ;
3. choisir la date, la banque, le compte, le libellé et l’association globale de repli ;
4. valider ;
5. l’application répartit le montant de base, crée les transactions non nulles et affecte le surplus à la réserve manuelle ;
6. en cas d’erreur, toutes les écritures sont annulées.

### 8.4 Restituer une réserve

1. choisir l’amortissement ;
2. sélectionner une restitution ;
3. saisir un montant inférieur ou égal au solde ;
4. compléter les informations de transaction ;
5. valider pour créer un revenu et diminuer le solde dans la même transaction SQLite.

## 9. Validations, erreurs et intégrité

Au démarrage, `verify_database()` contrôle :

- la présence des tables `transactions`, `libelles`, `sous_categorie`, `categories`, `amortissement`, `comptes`, `prelevementMensualise` et `emprunts` ;
- la présence de `categories.exclu` ;
- la présence de `transactions.dateTimestamp_forcee` ;
- la présence des associations catégorie/sous-catégorie des amortissements ;
- les colonnes nécessaires aux mensualités et emprunts ;
- `PRAGMA integrity_check` ;
- `PRAGMA foreign_key_check`.

Principales validations métier :

- textes obligatoires non vides ;
- catégories et sous-catégories actives ;
- cohérence parent/enfant ;
- montants positifs ou nuls selon le contexte ;
- objectif strictement positif ;
- nombre de mois strictement positif ;
- jour de prélèvement entre 1 et 31 ;
- restant d’emprunt compris entre 0 et le montant emprunté ;
- restitution limitée au solde disponible ;
- mensualité globale au moins égale au total normal.

Les erreurs de formulaire sont interceptées et présentées à l’utilisateur. Les écritures multi-étapes sont annulées intégralement si une étape échoue.

## 10. Installation et démarrage

### 10.1 Prérequis

- Python 3.11 ou plus récent recommandé ;
- accès en lecture/écriture au fichier SQLite ;
- environnement local capable d’ouvrir un navigateur.

### 10.2 Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### 10.3 Linux/macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

L’URL locale habituelle est `http://localhost:8501`.

### 10.4 Chemin de la base

Chemin par défaut : `data/budget.db`.

Pour utiliser une autre base :

```powershell
$env:BUDGET_DB_PATH="C:\chemin\budget.db"
```

```bash
BUDGET_DB_PATH=/chemin/budget.db streamlit run app.py
```

## 11. Déploiement et mise à jour

1. arrêter Streamlit avec `Ctrl+C` ;
2. sauvegarder le fichier SQLite ;
3. extraire l’archive de code dans le dossier du projet ;
4. remplacer les fichiers de code demandés ;
5. ne jamais remplacer la base locale par une base provenant d’une archive ;
6. mettre à jour les dépendances seulement si `requirements.txt` a changé ;
7. exécuter les tests ;
8. relancer Streamlit et effectuer un contrôle fonctionnel rapide.

Les archives de mise à jour doivent contenir uniquement le code, la documentation et les tests. Elles ne doivent contenir aucun fichier `.db`, `.sqlite` ou `.sqlite3`.

## 12. Alimentation Talend

Talend est responsable de l’extraction, du mapping et du chargement initial des relevés. L’application ne déclenche pas les traitements Talend.

Recommandations d’intégration :

- sauvegarder SQLite avant chaque import important ;
- conserver les identifiants bancaires stables lorsqu’ils existent ;
- convertir les montants en nombres avant insertion ;
- stocker les dépenses en négatif et les revenus en positif ;
- dédupliquer le flux avec `tUniqRow` et protéger également la base contre les rechargements historiques ;
- ne pas écraser les champs manuels `id_categorie_forcee`, `id_sous_categorie_forcee`, `dateTimestamp_forcee`, `type_mouvement` et `commentaire` lors d’une mise à jour ;
- respecter les clés étrangères et vérifier leur intégrité après import ;
- fermer l’application ou coordonner les écritures lors d’un chargement massif.

## 13. Tests et recette

### 13.1 Exécution automatisée

```bash
python -m unittest discover -s tests -v
python -m py_compile app.py db.py analytics.py
```

Les tests présents couvrent notamment : intégrité SQLite, chargements, persistance des modifications, dates forcées, relations de référentiels, exclusions analytiques, calculs d’amortissement, répartitions au centime, atomicité, mensualités, suivi, emprunts, soldes, filtre non catégorisé et sélection périmée.

### 13.2 Scénarios de recette prioritaires

| ID | Scénario | Résultat attendu |
|---|---|---|
| REC-01 | Activer « Uniquement non catégorisées » | Seules les lignes sans catégorie calculée ni forcée restent visibles |
| REC-02 | Catégoriser la première ligne du filtre | La ligne disparaît, aucune `IndexError`, la liste restante reste utilisable |
| REC-03 | Forcer une catégorie exclue | La transaction reste visible dans Transactions mais sort des statistiques |
| REC-04 | Forcer puis supprimer une date | La date forcée pilote d’abord les écrans, puis la date bancaire redevient effective |
| REC-05 | Choisir une sous-catégorie incompatible | Le choix est refusé ou remis à Aucune |
| REC-06 | Enregistrer une mensualité globale exacte | Une transaction non nulle par amortissement éligible, aucun surplus |
| REC-07 | Enregistrer un montant avec surplus | Transaction Épargne créée et réserve manuelle augmentée |
| REC-08 | Saisir un montant global insuffisant | Refus sans aucune écriture partielle |
| REC-09 | Restituer plus que le solde | Refus sans transaction ni modification du solde |
| REC-10 | Mettre un emprunt à zéro | Il disparaît de la liste des emprunts actifs |

### 13.3 Critères d’acceptation généraux

- aucune erreur Python visible pendant les parcours nominaux ;
- données persistantes après redémarrage ;
- intégrité et clés étrangères valides ;
- résultats financiers au centime ;
- cache actualisé immédiatement après écriture ;
- base absente des archives de mise à jour.

## 14. Exploitation, sauvegarde et sécurité

BudgetBibis est conçu pour un usage personnel local. Il ne comporte actuellement ni authentification ni gestion de rôles. Il ne doit donc pas être exposé directement sur Internet.

Bonnes pratiques :

- limiter les droits du fichier SQLite à l’utilisateur concerné ;
- effectuer des sauvegardes datées avant imports Talend et changements importants ;
- tester périodiquement la restauration d’une sauvegarde ;
- ne pas synchroniser la base vers un dépôt Git public ;
- ne jamais inclure la base ou des relevés dans une archive de code ;
- arrêter proprement Streamlit avant remplacement du code ou de la base ;
- conserver les journaux Talend nécessaires au diagnostic sans y exposer de données sensibles.

Le paramétrage SQLite utilise un délai d’attente de 10 000 ms pour les verrous, mais l’application reste destinée à un usage peu concurrent.

## 15. Maintenance et évolutions

### 15.1 Principes de maintenance

- placer l’accès aux données et les règles transactionnelles dans `db.py` ;
- placer les calculs indépendants de l’IHM dans `analytics.py` pour les tester facilement ;
- conserver `app.py` pour l’affichage et l’orchestration ;
- ajouter un test de régression pour chaque anomalie corrigée ;
- ne jamais renommer une colonne historique sans migration explicite ;
- maintenir la priorité des champs forcés sur les champs calculés.

### 15.2 Évolutions envisageables

- migrations SQLite versionnées ;
- journal d’audit des corrections manuelles ;
- import Talend contrôlé par lot avec identifiant de source ;
- contraintes ou index uniques adaptés aux identifiants bancaires ;
- export CSV/PDF des tableaux de bord ;
- sauvegarde guidée depuis l’interface ;
- découpage de `app.py` en pages ou composants ;
- tests d’interface Streamlit ;
- configuration externalisée des banques et comptes ;
- authentification si l’application devient accessible sur un réseau.

## 16. Matrice de traçabilité synthétique

| Domaine | Interface | Logique principale | Persistance | Tests |
|---|---|---|---|---|
| Filtres et transactions | `app.py` | `analytics.uncategorized_mask`, `selected_transaction_id` | `db.update_transaction` | `test_filters.py`, tests de transaction |
| Tableau de bord | `app.py` | `analytics.py` | Lecture `transactions` | tests d’agrégats et d’exclusion |
| Référentiels | `app.py` | validations `db.py` | `categories`, `sous_categorie`, `libelles` | création, renommage, suppression |
| Mensualités | `app.py` | normalisation/validation `db.py` | `prelevementMensualise` | CRUD et atomicité |
| Suivi | `app.py` | `monthly_follow_up`, `monthly_debits_remaining` | `budgetbibis_settings` | calculs et persistance |
| Emprunts | `app.py` | validation et avancement `db.py` | `emprunts` | mise à jour et bornes |
| Amortissements | `app.py` | calculs, répartition, atomicité `db.py` | `amortissement`, `transactions`, `comptes` | progression, contribution, restitution |

