LSN PHARMA — Livraison V4.9

Évolutions principales :
- nouvel onglet Historique réservé au profil Pharmacien ;
- recherche d’une livraison par pharmacie, code pharmacie, tournée, opérateur ou numéro de bac ;
- conservation dans l’historique de la date/heure, de l’opérateur, de la tournée, des bacs chargés/livrés/restitués, des colis chargés/livrés, des validations manuelles et anomalies ;
- une livraison validée peut être rouverte et corrigée tant que la tournée n’est pas clôturée, notamment pour ajouter un bac restitué oublié ;
- rollback du stock de bacs lors de la réouverture, puis nouveau calcul lors de la revalidation ;
- bouton final simplifié « TERMINER LA TOURNÉE » ; la clôture archive les données puis remet à zéro l’état opérationnel de la tournée, sans perdre le parc de bacs ;
- suppression du message « Livraison conforme et enregistrée » ;
- Back-office : bouton « ENREGISTRER » qui ferme la gestion de la tournée et revient à la liste des tournées ;
- KPI et Historique réservés au profil Pharmacien.

Prototype GitHub Pages : ne pas saisir de vrais codes d’alarme, porte ou interphone tant qu’une authentification et un stockage serveur sécurisés ne sont pas en place.

Pour GitHub Pages : remplacer index.html, sw.js, manifest.webmanifest et README.txt à la racine du dépôt.
