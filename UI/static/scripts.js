document.addEventListener('DOMContentLoaded', () => {
    // Funkcja do ładowania danych w tabeli
    const loadTableData = (url, sectionId) => {
        fetch(url)
            .then(response => response.json())
            .then(data => {
                const tbody = document.querySelector(`#${sectionId}Table tbody`);
                tbody.innerHTML = ''; // Wyczyść aktualne dane

                // Mapowanie danych w zależności od sekcji
                const columnMappings = {
                    readers: {
                        numer_karty: 'Numer Karty',
                        imie: 'Imię',
                        nazwisko: 'Nazwisko',
                        data_urodzenia: 'Data Urodzenia'
                    },
                    books: {
                        id_ksiazki: 'ID',
                        tytul: 'Tytuł',
                        autor: 'Autor',
                        rok_wydania: 'Rok Wydania',
                        isbn: 'ISBN',
                        kategoria: 'Kategoria',
                        dostepnosc: 'Dostępność'
                    },
                    borrowings: {
                        id_wypozyczenia: 'ID',
                        ksiazka_id: 'ID Książki',
                        data_wypozyczenia: 'Data Wypożyczenia',
                        data_zwrotu: 'Data Zwrotu',
                        czytelnik_id: 'ID Czytelnika'
                    }
                };

                const mappings = columnMappings[sectionId];

                data.forEach(item => {
                    const row = document.createElement('tr');
                    Object.keys(mappings).forEach(key => {
                        const cell = document.createElement('td');
                        if (key === 'dostepnosc' && sectionId === 'books') {
                            cell.innerHTML = item[key] ? '✔️' : '❌';
                        } else {
                            cell.textContent = item[key] !== undefined ? item[key] : 'Brak';
                        }
                        row.appendChild(cell);
                    });

                    // Dodanie przycisku usuwania i przycisku zwrotu w zależności od sekcji
                    const actionCell = document.createElement('td');

                    if (sectionId === 'readers') {
                        const deleteButton = document.createElement('button');
                        deleteButton.textContent = 'Usuń';
                        deleteButton.className = 'delete-btn';
                        deleteButton.dataset.cardNumber = item.numer_karty;
                        actionCell.appendChild(deleteButton);
                    } else if (sectionId === 'books') {
                        const deleteButton = document.createElement('button');
                        deleteButton.textContent = 'Usuń';
                        deleteButton.className = 'delete-btn';
                        deleteButton.dataset.bookId = item.id_ksiazki;
                        actionCell.appendChild(deleteButton);
                    } else if (sectionId === 'borrowings') {
                        if (!item.data_zwrotu) {
                            const returnButton = document.createElement('button');
                            returnButton.textContent = 'Zwróć';
                            returnButton.className = 'return-btn';
                            returnButton.dataset.borrowId = item.id_wypozyczenia;
                            actionCell.appendChild(returnButton);
                        }

                        const deleteButton = document.createElement('button');
                        deleteButton.textContent = 'Usuń';
                        deleteButton.className = 'delete-btn';
                        deleteButton.dataset.borrowId = item.id_wypozyczenia;
                        actionCell.appendChild(deleteButton);
                    }
                    row.appendChild(actionCell);

                    tbody.appendChild(row);
                });

                // Dodanie obsługi kliknięcia w przyciski usuwania
                document.querySelectorAll('.delete-btn').forEach(button => {
                    button.addEventListener('click', () => {
                        let apiUrl, data;
                        if (button.dataset.cardNumber) {
                            apiUrl = '/delete_reader';
                            data = { card_num: button.dataset.cardNumber };
                        } else if (button.dataset.bookId) {
                            apiUrl = '/delete_book';
                            data = { book_id: button.dataset.bookId };
                        } else if (button.dataset.borrowId) {
                            apiUrl = '/delete_borrowing';
                            data = { borrow_id: button.dataset.borrowId };
                        }

                        fetch(apiUrl, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded'
                            },
                            body: new URLSearchParams(data)
                        })
                        .then(response => {
                            if (response.ok) {
                                loadTableData(url, sectionId); // Odśwież tabelę
                                if (sectionId === 'borrowings'){
                                    loadTableData('/fetch_books', 'books')
                                }

                            } else {
                                alert('Błąd podczas usuwania');
                            }
                        })
                        .catch(error => console.error('Błąd podczas usuwania:', error));
                    });
                });

                // Dodanie obsługi kliknięcia w przyciski zwrotu
                document.querySelectorAll('.return-btn').forEach(button => {
                    button.addEventListener('click', () => {
                        const borrowId = button.dataset.borrowId;
                        fetch('/return_borrow', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded'
                            },
                            body: new URLSearchParams({
                                borrow_id: borrowId
                            })
                        })
                        .then(response => {
                            if (response.ok) {
                                loadTableData(url, sectionId);
                                loadTableData('/fetch_books', 'books')
                            } else {
                                alert('Błąd podczas zwracania wypożyczenia');
                            }
                        })
                        .catch(error => console.error('Błąd podczas zwracania:', error));
                    });
                });
            })
            .catch(error => console.error('Błąd podczas pobierania danych:', error));
    };

    // Ładowanie danych dla wszystkich sekcji przy załadowaniu strony
    document.querySelectorAll('.toggle-btn').forEach(button => {
        const sectionId = button.getAttribute('data-section');
        const url = button.parentElement.querySelector('.refresh-btn').getAttribute('data-url');

        // Ładowanie danych na początku
        loadTableData(url, sectionId);
    });

    // Obsługa przycisków rozwijania i zwijania
    document.querySelectorAll('.toggle-btn').forEach(button => {
        button.addEventListener('click', () => {
            const sectionId = button.getAttribute('data-section');
            const table = document.querySelector(`#${sectionId}Table`);
            const isHidden = table.classList.contains('hidden');
            table.classList.toggle('hidden', !isHidden);
            button.textContent = isHidden ? '▲' : '▼';
        });
    });

    // Obsługa przycisków odświeżania
    document.querySelectorAll('.refresh-btn').forEach(button => {
        button.addEventListener('click', () => {
            const url = button.getAttribute('data-url');
            const sectionId = button.parentElement.querySelector('.toggle-btn').getAttribute('data-section');
            loadTableData(url, sectionId);
        });
    });

    // Ustawienie początkowego stanu tabeli jako zwinięte
    document.querySelectorAll('.toggle-btn').forEach(button => {
        const sectionId = button.getAttribute('data-section');
        const table = document.querySelector(`#${sectionId}Table`);
        table.classList.add('hidden');
        button.textContent = '▼'; // Ustaw przycisk na znak rozwijania
    });
});
