function displayThisJson(data, player_id) {
	return () => {
		let this_data = data[player_id];
		let domNode = document.querySelector('#json');
		domNode.innerHTML = ""; // clear old data if it exists
		const tree = JsonView.renderJSON(this_data, domNode);
    	JsonView.expandChildren(tree); // Expand tree after rendering
	}
}

function deletePlayer(friendly_key) {
	return () => {
	    fetch(`/debug/players/${friendly_key}`, {method: 'DELETE'})
            .then(res => {
                if (res.ok) {
                    // redo setup
                    fetch('/debug/players').then(res => res.json()).then(data => setupTable(data));
                } else {
                    res.text().then(text => console.log(`Delete Failed: ${text}`));
                }
            })
	}
}

function setupTableHead(table) {
	let tHead = table.createTHead();
    let row = tHead.insertRow();
    let th = document.createElement("th");
    th.appendChild(document.createTextNode("Players"));
    row.appendChild(th);

    th = document.createElement("th");
    th.appendChild(document.createTextNode("Delete"));
    row.appendChild(th);
}

function setupTableRow(key, table, data) {
	let friendly_key = key.substring(5); // remove plr:+

	let row = table.insertRow();
	// display info
    let cell = row.insertCell();
    let displayInfo = document.createElement("input");
    displayInfo.type = "button";
    displayInfo.value = `View ${friendly_key}`;
    displayInfo.onclick = displayThisJson(data, key);
    cell.appendChild(displayInfo);

    cell = row.insertCell();
    let deleteButton = document.createElement("input");
    deleteButton.type = "button";
    deleteButton.value = `Delete ${friendly_key}`;
    deleteButton.onclick = deletePlayer(friendly_key);
    cell.appendChild(deleteButton);
}

function setupTable(data) {
	let table = u("#players").nodes[0];
	table.innerHTML = ""; // Delete anything that was there before
    setupTableHead(table);
    for (let key of Object.keys(data)) {
    	setupTableRow(key, table, data);
    }
}

fetch('/debug/players').then(res => res.json()).then(data => setupTable(data));