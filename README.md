# BudgetBibis

Application locale Streamlit de consultation et d'édition d'une base budgétaire SQLite.

## Fonctions

- indicateurs d'entrées, sorties, solde net et nombre d'opérations ;
- filtres par période, banque, compte, catégorie et texte ; le filtre « Uniquement non catégorisées » retient les transactions dont la catégorie calculée et la catégorie forcée sont toutes deux absentes ;
- graphiques mensuels et dépenses par catégorie ;
- exclusion des statistiques et graphiques des transactions dont la catégorie effective porte `exclu = 1` ;
- sélection d’un mois puis calcul du solde net de chaque catégorie (`revenus − dépenses`) : une catégorie au solde positif apparaît uniquement dans Revenus, une catégorie au solde négatif uniquement dans Dépenses, et une catégorie au solde nul dans aucun des deux tableaux ;
- affichage de toutes les lignes du tableau mensuel des dépenses sans redimensionnement manuel ni défilement interne ;
- calcul du solde mensuel `revenus − dépenses` sous les deux tableaux ;
- graphique en anneau des dépenses du mois sélectionné : pictogrammes représentatifs, mise en avant des 7 catégories principales, montant total central, pourcentages au survol et classement complet avec barres de proportion ;
- solde mensuel affiché en vert lorsqu’il est positif, en rouge lorsqu’il est négatif et en gris lorsqu’il est nul ;
- consultation de toutes les transactions, y compris celles exclues des statistiques ;
- sélection d’une ligne du tableau Transactions pour la pré-sélectionner dans le formulaire de modification ;
- catégories proposées par ordre alphabétique dans la modification d’une transaction ;
- filtrage immédiat des sous-catégories selon la catégorie forcée sélectionnée, avec tri alphabétique ; une sous-catégorie devenue incompatible est remise à « Aucune » ;
- édition persistante de la date effective forcée, de la catégorie forcée, de la sous-catégorie forcée, du type de mouvement et du commentaire ;
- conservation et affichage de la date bancaire originale ; la date forcée pilote les filtres, regroupements mensuels, graphiques et statistiques ;
- création de catégories, sous-catégories et règles de libellés ;
- renommage des catégories et sous-catégories sans casser leurs relations ;
- suppression confirmée d’une règle de libellé en conservant ses transactions ;
- onglet Amortissements avec consultation, création et modification des réserves ;
- association d’une catégorie et d’une sous-catégorie à chaque amortissement ;
- enregistrement global atomique des mensualités : une transaction négative par amortissement pour sa mensualité et son association propre, puis une transaction Épargne pour l’éventuel surplus affecté à `comptes.amortissementManuel` ; la somme des transactions égale le montant global ;
- affichage et modification indépendante du solde `amortissementManuel` ;
- restitution partielle ou totale : transaction positive et diminution du solde de l’amortissement ;
- modification manuelle de la date du dernier paiement effectif, jamais changée par une mensualité ;
- recalcul automatique de l’avancement financier, de la progression des mensualités, des mois restants et de la mensualité ajustée à chaque modification du solde ;
- affichage de l’avancement financier en vert uniquement lorsqu’il vaut exactement `100 %` ; les autres valeurs restent sans couleur ;
- onglet Mensualités : consultation, création, modification de tous les champs sauf l’identifiant et suppression confirmée des prélèvements mensualisés ;
- filtrage des sous-catégories selon la catégorie choisie et validation des associations ;
- onglet Suivi : mensualités Trade Republic, mensualités des amortissements, surplus souhaité persistant, solde du mois précédent persistant, somme mensuelle à transférer vers Trade Republic et minimum à conserver sur Trade Republic ;
- solde du mois précédent affiché dans le tableau de bord à côté du solde mensuel, avec un solde total calculé selon `solde du mois + solde du mois précédent` ;
- solde total prévisionnel affiché à droite du solde total et calculé selon `solde total − reste à prélever du mois` ;
- suivi séparé du reste à prélever à partir du jour courant pour chaque banque et compte, également affiché dans le tableau de bord, sans incidence sur le transfert Trade Republic ni sur le solde mensuel ;
- onglet Emprunts : liste des emprunts en cours, échéance, restant à rembourser modifiable et pourcentage d’avancement calculé ;
- activation systématique des clés étrangères SQLite.

## Installation

Python 3.11 ou plus récent est recommandé.

```bash
python -m venv .venv
```

Sous Windows PowerShell, sans activer l’environnement virtuel :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Sous Linux/macOS :

```bash
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

L'application s'ouvre normalement sur <http://localhost:8501>.

## Base de données

La base utilisée par défaut se trouve dans `data/budget.db`. **Les archives de mise à jour ne contiennent volontairement aucun fichier `.db`** : conserve ta base existante et remplace uniquement les fichiers de code. La catégorie effective est la catégorie forcée lorsqu’elle est renseignée, sinon la catégorie calculée. Si son champ `exclu` vaut `1`, la transaction est ignorée dans les statistiques et graphiques, mais demeure visible et éditable dans le tableau.

Une ancienne base doit posséder les colonnes suivantes :

```sql
ALTER TABLE categories
ADD COLUMN exclu INTEGER NOT NULL DEFAULT 0 CHECK (exclu IN (0,1));

ALTER TABLE transactions
ADD COLUMN dateTimestamp_forcee INTEGER;

ALTER TABLE amortissement
ADD COLUMN id_categorie INTEGER;

ALTER TABLE amortissement
ADD COLUMN id_sous_categorie INTEGER;
```

`dateTimestamp` demeure la date bancaire originale. Lorsque `dateTimestamp_forcee` est renseignée, elle devient la date effective utilisée dans toute l’application. Le formulaire permet de revenir à la date originale en remettant cette colonne à `NULL`.

Pour employer un autre fichier sans modifier le projet :

Sous Windows PowerShell :

```powershell
$env:BUDGET_DB_PATH="C:\chemin\budget.db"
streamlit run app.py
```

Sous Linux/macOS :

```bash
BUDGET_DB_PATH=/chemin/budget.db streamlit run app.py
```

Faire une sauvegarde du fichier SQLite avant les imports Talend ou les modifications importantes.

## Amortissements

L’onglet **Amortissements** utilise la table `amortissement` du nouveau modèle :

- les champs descriptifs et financiers sont modifiables et un nouvel amortissement peut être créé ;
- `id_categorie` et `id_sous_categorie` permettent de choisir l’association utilisée pour les transactions de mensualité ; la sous-catégorie est filtrée selon la catégorie et la cohérence est validée par l’application ;
- `AvancementPourcentage` correspond à l’avancement financier et est recalculé par `solde ÷ objectif × 100` ;
- `Progession_pourcentage` correspond au respect du rythme des mensualités et est recalculé par `((mois restant × mensualité ajustée) + solde) ÷ objectif × 100` : `100 %` signifie que le suivi est au bon rythme ;
- la progression des mensualités est colorée : rouge sous `70 %`, orange de `70 %` à `90 %` inclus, vert au-dessus de `90 %` ; l’avancement financier est vert uniquement à exactement `100 %` et reste sans couleur dans tous les autres cas ;
- la modification manuelle du solde, une mensualité globale, une contribution ou une restitution recalculent les deux pourcentages sans jamais remplacer `Progession_pourcentage` par l’avancement financier ;
- `Mois_restant` est recalculé entre la date courante (ou la date de l’opération) et `date_cible` ;
- `mensualite_ajustee` vaut `0` lorsque l’avancement financier atteint ou dépasse `100 %` ; sinon, elle est égale à la `mensualite` normale ;
- la somme globale préremplie correspond à la somme de toutes les colonnes `mensualite` augmentée du surplus souhaité enregistré dans l’onglet **Suivi** ;
- une saisie inférieure à cette somme est refusée ;
- le montant global de base reste calculé avec la somme des `mensualite` normales, puis il est réparti proportionnellement selon les `mensualite_ajustee` positives ; une transaction négative est créée pour chaque amortissement recevant une part et aucune transaction à `0 €` n’est créée ;
- si un amortissement n’a aucune association, la catégorie et la sous-catégorie globales servent de repli ;
- le surplus crée une transaction négative supplémentaire de type Épargne, utilise l’association globale et est ajouté à `comptes.amortissementManuel` ;
- la somme de toutes les transactions créées correspond exactement au montant global saisi ;
- le solde `amortissementManuel` est affiché et peut être modifié sans effet sur les transactions ou amortissements ;
- une restitution crée une transaction positive et diminue le solde de l’amortissement sélectionné du même montant ;
- transaction et mises à jour des soldes sont enregistrées dans une même transaction SQLite ;
- `dateDernierPaiment` reste exclusivement modifiable dans le formulaire de l’amortissement.

Les noms de colonnes historiques `Progession_pourcentage` et `dateDernierPaiment` sont conservés pour rester compatibles avec la base existante.

## Mensualités et suivi

L’onglet **Mensualités** utilise la table `prelevementMensualise`. Les champs `nom`, `mensualite`, `methode_paiment`, `jourDePrelevement`, `ancienneMensualite`, `id_categorie`, `id_sous_categorie`, `banque` et `compteBancaire` sont modifiables ; seul `id` reste immuable. Le jour de prélèvement doit être compris entre `1` et `31`.

L’onglet **Suivi** rapproche les lignes dont `banque` correspond à `Trade Republic`, sans tenir compte de la casse ni des espaces de début et de fin :

- **Mensualités Trade Republic** : somme mensuelle complète ;
- **Mensualités des amortissements** : somme des mensualités de la table `amortissement` ;
- **Surplus souhaité** : valeur persistante saisie par l’utilisateur ;
- **Somme à transférer mensuellement vers Trade Republic** : mensualités Trade Republic + mensualités des amortissements + surplus ;
- **Minimum montant Trade Republic** : mensualités Trade Republic + somme des soldes de tous les amortissements + solde du compte `amortissementManuel`.

Le **reste à prélever ce mois** est présenté dans un bloc distinct. Il couvre toutes les banques et tous les comptes de `prelevementMensualise`, regroupés par couple `banque` / `compteBancaire`, et retient les mensualités dont `jourDePrelevement` est supérieur ou égal au jour courant. Cette information apparaît aussi dans le tableau de bord, à côté du solde mensuel. Elle ne modifie ni le solde du mois ni la somme à transférer vers Trade Republic ; elle est uniquement déduite du solde total pour établir le prévisionnel.

Le **solde du mois précédent** est saisi et enregistré dans l’onglet Suivi, puis affiché à côté du solde calculé du mois dans le tableau de bord. Il accepte une valeur positive, nulle ou négative. Le **solde total** est calculé par `solde du mois + solde du mois précédent`. À sa droite, le **solde total prévisionnel** est calculé par `solde total − reste à prélever du mois`. Ces deux soldes reprennent la coloration verte, rouge ou grise selon leur signe. Le solde précédent ne modifie pas le transfert Trade Republic.

Le surplus et le solde du mois précédent sont conservés dans une table applicative créée automatiquement dans la base :

```sql
CREATE TABLE IF NOT EXISTS budgetbibis_settings (
    cle TEXT PRIMARY KEY,
    valeur_reelle REAL NOT NULL
);
```

## Emprunts

L’onglet **Emprunts** utilise la table `emprunts` et affiche uniquement les lignes dont `restantARembourse` est strictement positif. Il présente le nom, le montant emprunté, le restant à rembourser, la date de fin et l’avancement calculé ainsi :

```text
(montantEmprunte − restantARembourse) / montantEmprunte × 100
```

Le résultat est borné entre `0 %` et `100 %` et s’affiche sans coloration. Seul `restantARembourse` est modifiable dans l’interface ; il doit être compris entre `0` et `montantEmprunte`. Lorsqu’il atteint `0`, l’emprunt n’apparaît plus parmi les emprunts en cours.
# BibisBudget
