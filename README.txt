LSN PHARMA — Livraison V5.2

Évolutions principales :
- Historique Pharmacien enrichi avec heure de départ, heure de fin et durée réelle de chaque tournée ;
- heure de passage et heure de validation affichées pour chaque pharmacie ;
- une tournée sélectionnée pour le chargement devient la tournée opérationnelle active : aucune autre tournée ne peut être sélectionnée avant sa clôture ;
- dès que le mode Livraison a commencé, l’onglet Chargement renvoie vers la livraison en cours jusqu’à la clôture ;
- écran Tournées : seule la tournée active peut être reprise, les autres sont indisponibles pendant l’opération ;
- création de tournée avec numérotation automatique incrémentale : Tournée 01, 02, 03, 04, etc. ;
- le champ de création ne sert plus qu’à saisir un libellé facultatif (ex. Paris Sud) ;
- suppression de l’affichage « Code pharmacie : PH-xxxxxx » dans la fiche de gestion d’une tournée du Back-office ;
- le code pharmacie reste disponible en mode Livraison pour l’identification terrain ;
- conservation de toutes les règles V5.0 : historique Jour > Tournée > Pharmacie, unicité stricte des bacs, libération « Restitué à l’entrepôt », parc de bacs persistant et remise à zéro opérationnelle à la clôture.

KPI et Historique restent réservés au profil Pharmacien.

Prototype GitHub Pages : ne pas saisir de vrais codes d’alarme, porte ou interphone tant qu’une authentification et un stockage serveur sécurisés ne sont pas en place.

Pour GitHub Pages : remplacer index.html, sw.js, manifest.webmanifest et README.txt à la racine du dépôt.


V5.2 : une tournée n’est verrouillée qu’après un chargement réel (au moins un bac ou un colis) ou le démarrage de la livraison. Tant que rien n’est chargé, l’opérateur peut revenir à Tournées et en choisir une autre. Les anciens chargements résiduels sans tournée active sont nettoyés automatiquement et ne sont plus comptés comme « chargés ».
