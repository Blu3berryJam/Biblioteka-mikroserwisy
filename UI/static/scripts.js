// static/scripts.js

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
                        id: 'ID',
                        tytul: 'Tytuł',
                        autor: 'Autor',
                        rok_wydania: 'Rok Wydania',
                        isbn: 'ISBN',
                        kategoria: 'Kategoria',
                        dostepnosc: 'Dostępność'
                    },
                    borrowings: {
                        id: 'ID',
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
                        cell.textContent = item[key] !== undefined ? item[key] : 'Brak';
                        row.appendChild(cell);
                    });
                    tbody.appendChild(row);
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
