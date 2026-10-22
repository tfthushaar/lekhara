# Lekhara Connector for Tally

The Lekhara Connector runs on the computer that has Tally, and brings your books into Lekhara by itself: every few minutes it reads Tally's masters and recent vouchers, and once a night the whole financial year, and sends them to your project in Lekhara.

- **Nothing in Tally is changed.** The connector only reads.
- **Nothing is opened to the internet.** The connector makes outgoing connections only: to Tally on the same computer, and to Lekhara.
- **Nothing comes in twice.** Lekhara matches every voucher on Tally's own identity, so the same voucher sent again adds nothing.
- **What needs a choice waits.** A buyer's ledger with no unit yet, or an expense ledger with no cost line, waits in Lekhara's review queue; once you choose, it comes in on the next sync.

## Setting it up

1. **Turn on Tally's HTTP server.** In TallyPrime: Help, Settings, Connectivity. Set TallyPrime to act as a server (or both) on port 9000. Keep Tally open with the company loaded.
2. **Get a code.** In Lekhara, open the project's Import page, then "Or connect Tally, so it comes in by itself", and press "Get a code". The code works once, for 30 minutes.
3. **Link the computer.** On the Tally computer, open a command prompt in the folder with the connector and run:

   ```
   lekhara-connector link ABCD-EFGH --server https://your-lekhara-address
   ```

   If more than one company is open in Tally, add `--company "Your Company Name"`. If Tally runs on another computer in the office, add `--tally http://that-computer:9000`.
4. **Start it.** Run `lekhara-connector run` and leave it running. To start it with Windows, add a task in the Task Scheduler that runs `lekhara-connector run` when you sign in, or `lekhara-connector once` every 15 minutes.

`lekhara-connector status` shows what it last did. To stop, unlink the computer on the Import page (the connector stops at once) and run `lekhara-connector unlink` on the computer.

## What it needs

- Windows with TallyPrime (or Tally.ERP 9 with its ODBC/HTTP server on).
- Either the packaged `lekhara-connector.exe`, or Python 3.10 or later with `lekhara_connector.py` (it uses only Python's standard library).

## Building the Windows program

On a Windows computer with Python:

```
powershell -ExecutionPolicy Bypass -File build.ps1
```

This makes `dist\lekhara-connector.exe`, a single program with nothing else to install. Sign it with the firm's code-signing certificate before handing it out, so Windows does not warn about it.

## How often it asks Tally

Every few minutes the connector asks Tally for two numbers: the last change number of the company's masters and of its vouchers (Tally's AlterIDs). Only when one has moved does it export, so a quiet Tally is never slowed by exports. Once a day it exports the whole financial year regardless, and with an older Tally that cannot give the numbers it exports the last week each time and sends it only if it changed.
