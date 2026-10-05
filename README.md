# e621-tags-edit

La section `[SET]` de `config.txt` doit contenir le shortname d'un set e621
existant. Quand vous utilisez « Skip », le post est ajouté à ce set avant de
passer au suivant; l'ajout API se termine en arrière-plan. Les posts de ce set
sont exclus des recherches suivantes.

Les actions « Submit » et « Skip » passent au post suivant immédiatement.
Les requêtes API sont envoyées en arrière-plan, dans l'ordre, tandis que
l'image du post courant se charge séparément. Une erreur API affiche le numéro
du post concerné afin de pouvoir le retrouver et vérifier l'action.
Les raccourcis clavier sont Enter pour « Submit », flèche droite pour « Skip »
et flèche gauche pour revenir au post précédent. Ils ne s'appliquent pas quand
le focus est dans un champ de saisie.

Au démarrage, le programme lit le quota d'éditions de tags restant sur e621
et l'affiche. Le compteur local diminue après chaque « Submit » réussi; « Skip »
ne le change pas. Le quota est relu automatiquement après chaque tranche de
15 « Submit » réussis pour tenir compte des éditions qui sortent de la fenêtre
d'une heure.