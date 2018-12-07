# simple-game-shop-server

## Description
simple-game-shop-server is a socket-based server used to handle requests to database containing information about shop,
users and users' inventories.

List of implemented commands:

- `LOGIN <nickname>` - Sign in to the server
- `LOGOUT` - Sign out from the server
- `SHOPLIST` - List shop items
- `INVENTORY` - List purchased items
- `BALANCE` - Show available credits
- `BUY <item_name>` - Buy item in shop
- `SELL <item_name>` - Sell item from your inventory

Client for this server: https://github.com/mckunda/simple-game-shop-client
 

## Python version

python-3.6.4

## How to use

- clone this repo
- cd into project
- install dependencies:
```bash
$ pip install -r requirements.txt
```
- run `main.py`:
```bash
python main.py
```

## Database
Note that data set provided in `data/db.json` is **example data** from http://wiki.wargaming.net/en/World_of_Warships.

If you want to provide your `shop_items` table data, you must meet these requirements:
- the "bare-bones" `db.json` file must look like this:
```json
{
  "_default": {},
  "shop_items": {
  }
}
```
- with added shop items it must look like this:
```json
{
  "_default": {},
  "shop_items": {
    "1": {"name": "Apple", "price": 10},
    "2": {"name": "", "price": 7500},
    "3": {"name": "IndiaYankee", "price": 6000}
  }
}
```
- you **MUST NOT** corrupt the structure of db.json.
- if you want to fill the `shop_items` table using python, consider using TinyDB: https://tinydb.readthedocs.io/en/latest/