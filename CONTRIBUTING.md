# Linee guida per la contribuzione

Contribuire a questo progetto deve essere il più semplice e trasparente possibile, che si tratti di:

- Segnalare un bug
- Discutere lo stato attuale del codice
- Inviare una correzione
- Proporre nuove funzionalità

## GitHub viene usato per tutto

Usiamo GitHub per ospitare il codice, tracciare i problemi (issue), le richieste di funzionalità e accettare le Pull Request.

Le Pull Request sono il modo migliore per proporre modifiche:

1. Fai un Fork del repo e crea il tuo branch da `main`.
2. Se modifichi qualcosa, aggiorna la documentazione.
3. Assicurati che il codice superi il linting (usando ruff/black).
4. Testa il tuo contributo.
5. Invia la Pull Request!

## Licenza MIT

Ogni contributo inviato sarà rilasciato sotto la stessa [Licenza MIT](http://choosealicense.com/licenses/mit/) che copre il progetto.

## Segnalazione dei Bug

Usa le [Issue di GitHub](../../issues) per segnalare bug pubblici. Sii specifico e includi:
- Un riassunto rapido.
- Passaggi per riprodurre il problema.
- Risultato atteso vs Risultato ottenuto.

## Stile del Codice

Usa [ruff](https://github.com/astral-sh/ruff) (che sostituisce black e flake8) e [prettier](https://prettier.io/) per mantenere lo stile uniforme.
In alternativa, usa i `pre-commit` già configurati in questo repository.

## Testa le tue modifiche

Questa integrazione è nata originariamente da un blueprint, ma ora è un progetto autonomo chiamato **BLE Radar**.

Il progetto include un ambiente di sviluppo in container, facile da avviare con Visual Studio Code. Avrai un'istanza di Home Assistant isolata e già configurata tramite il file [`.devcontainer.json`](./.devcontainer.json).

Verifica sempre che i [test](./tests) esistenti funzionino ancora ed è caldamente consigliato aggiungerne di nuovi. Puoi avviare i test dalla root con:

`./scripts/test`

## Pre-commit

Puoi usare i settaggi di [pre-commit](https://pre-commit.com/) inclusi nel repository per i controlli automatici.
Con lo strumento installato, attiva i settaggi con:

```console
$ pre-commit install
