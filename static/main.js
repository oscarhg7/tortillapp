/**
 * Navega a la sección de añadir tortilla
 * Si estás en index, muestra la sección; si no, redirige a la página de inicio
 */
function goToAdd() {
    const addSection = document.getElementById('add');
    if (addSection) {
        // Estamos en index.html, mostrar la sección
        showSection('add');
        // Desplazar hacia arriba
        window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
        // Estamos en otra página, redirigir a inicio
        window.location.href = '/';
    }
}

/**
 * Inicializa el autocomplete de ubicación
 */
function initLocationAutocomplete() {
    const locationInput = document.getElementById('location');
    const suggestionsList = document.getElementById('location-suggestions');
    
    if (!locationInput || !suggestionsList) return;
    
    let searchTimeout;
    
    locationInput.addEventListener('input', function() {
        const query = this.value.trim();
        
        // Limpiar timeout anterior
        clearTimeout(searchTimeout);
        
        // Si el campo está vacío, ocultar sugerencias
        if (query.length < 2) {
            suggestionsList.classList.remove('active');
            return;
        }
        
        // Esperar 300ms antes de hacer la búsqueda (debounce)
        searchTimeout = setTimeout(() => {
            searchLocations(query, suggestionsList);
        }, 300);
    });
    
    // Cerrar sugerencias si haces clic fuera
    document.addEventListener('click', function(event) {
        if (event.target !== locationInput) {
            suggestionsList.classList.remove('active');
        }
    });
}

/**
 * Busca ubicaciones usando Nominatim (OpenStreetMap)
 * @param {string} query - Texto de búsqueda
 * @param {HTMLElement} suggestionsList - Contenedor de sugerencias
 */
function searchLocations(query, suggestionsList) {
    // Usar Nominatim API de OpenStreetMap (gratuita y sin API key)
    const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=8&countrycodes=es`;
    
    fetch(url)
        .then(response => response.json())
        .then(results => {
            if (results.length === 0) {
                suggestionsList.innerHTML = '<div class="location-suggestion-item" style="color: #64748b;">No se encontraron resultados</div>';
                suggestionsList.classList.add('active');
                return;
            }
            
            // Mostrar sugerencias
            suggestionsList.innerHTML = results.map(result => {
                const mainName = result.name || result.address?.road || result.address?.city || '';
                const detail = result.address?.city && result.address.city !== mainName ? result.address.city : (result.address?.country || '');
                const label = `${mainName}${detail ? ', ' + detail : ''}`;

                return `
                    <div class="location-suggestion-item" onclick="selectLocation('${label.replace(/'/g, "\\'")}', '${result.lat}', '${result.lon}')">
                        <div class="location-suggestion-main">${mainName}</div>
                        ${detail ? `<div class="location-suggestion-detail">${detail}</div>` : ''}
                    </div>
                `;
            }).join('');
            
            suggestionsList.classList.add('active');
        })
        .catch(error => {
            console.error('Error en búsqueda de ubicación:', error);
            suggestionsList.innerHTML = '<div class="location-suggestion-item" style="color: #ef4444;">Error en la búsqueda</div>';
            suggestionsList.classList.add('active');
        });
}

/**
 * Selecciona una ubicación y la guarda en el campo
 * @param {string} location - Ubicación seleccionada
 */
function selectLocation(location, lat, lng) {
    const locationInput = document.getElementById('location');
    const suggestionsList = document.getElementById('location-suggestions');

    if (locationInput) {
        locationInput.value = location;
        const latInput = document.getElementById('latitude');
        const lngInput = document.getElementById('longitude');
        if (latInput) latInput.value = lat || '';
        if (lngInput) lngInput.value = lng || '';
        suggestionsList.classList.remove('active');
    }
}

/**
 * Muestra una sección específica y oculta las demás
 * @param {string} sectionId - ID de la sección a mostrar
 */
function showSection(sectionId) {
    try {
        // Validar que el ID sea válido
        if (!sectionId || typeof sectionId !== 'string') {
            console.error('ID de sección inválido');
            return;
        }

        // Ocultar todas las secciones
        const sections = document.querySelectorAll('.section');
        sections.forEach(section => {
            section.classList.remove('active');
        });

        // Mostrar la sección seleccionada
        const targetSection = document.getElementById(sectionId);
        if (targetSection) {
            targetSection.classList.add('active');
            console.log(`Sección ${sectionId} activada`);
        } else {
            console.warn(`No se encontró la sección: ${sectionId}`);
        }
    } catch (error) {
        console.error('Error al cambiar sección:', error);
    }
}

/**
 * Maneja los likes de las tortillas con petición al servidor
 * @param {number} tortillaId - ID de la tortilla
 */
function like(tortillaId) {
    try {
        // Validar que el ID sea un número
        if (!tortillaId || isNaN(tortillaId)) {
            console.error('ID de tortilla inválido');
            return;
        }

        // Hacer petición al servidor
        const url = `/like/${tortillaId}`;
        
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                console.error('Error del servidor:', data.error);
                // Redirigir a login si es necesario
                if (data.error.includes('login')) {
                    window.location.href = '/login';
                }
                return;
            }

            // Actualizar el contador de likes
            const likesSpan = document.getElementById(`likes-${tortillaId}`);
            if (likesSpan) {
                likesSpan.textContent = data.likes;
                
                // Animación visual
                likesSpan.classList.add('like-animation');
                setTimeout(() => {
                    likesSpan.classList.remove('like-animation');
                }, 300);
            }

            console.log(`Like procesado para tortilla ${tortillaId}`);
        })
        .catch(error => {
            console.error('Error al procesar like:', error);
            alert('Error al procesar el like. Por favor, inténtalo de nuevo.');
        });
    } catch (error) {
        console.error('Error en función like:', error);
    }
}

/**
 * Inicializa la aplicación al cargar la página
 */
function initializeApp() {
    try {
        // Si hay un hash en la URL (ej: #add), mostrar esa sección
        const hash = window.location.hash.substring(1);
        if (hash && hash === 'add') {
            const addSection = document.getElementById('add');
            if (addSection) {
                showSection('add');
                return;
            }
        }
        
        // Si no hay hash, mostrar la sección de feed por defecto (solo si existe)
        const feedSection = document.getElementById('feed');
        if (feedSection) {
            showSection('feed');
        }
        
        // Inicializar autocomplete de ubicación
        initLocationAutocomplete();

        // Inicializar carruseles de fotos
        initCarousels();

        console.log('Aplicación inicializada correctamente');
    } catch (error) {
        console.error('Error en inicialización:', error);
    }
}

// Ejecutar inicialización cuando el DOM esté listo
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}

/**
 * Inicializa los carruseles de fotos con scroll-snap y puntos indicadores
 */
function initCarousels() {
    document.querySelectorAll('.carousel-track').forEach(track => {
        const carouselEl = track.closest('.photo-carousel');
        if (!carouselEl) return;

        const carouselId = carouselEl.id.replace('carousel-', '');
        const dots = document.querySelectorAll(`.carousel-dot[data-carousel="${carouselId}"]`);

        if (dots.length === 0) return;

        // Actualizar punto activo al deslizar
        track.addEventListener('scroll', () => {
            const index = Math.round(track.scrollLeft / track.clientWidth);
            dots.forEach((dot, i) => dot.classList.toggle('active', i === index));
        }, { passive: true });

        // Clic en punto para ir a esa foto
        dots.forEach(dot => {
            dot.addEventListener('click', () => {
                const index = parseInt(dot.dataset.index);
                track.scrollTo({ left: index * track.clientWidth, behavior: 'smooth' });
            });
        });
    });
}

/**
 * Manejo global de errores
 */
window.addEventListener('error', function(event) {
    console.error('Error global:', event.error);
});

window.addEventListener('unhandledrejection', function(event) {
    console.error('Promesa rechazada sin manejar:', event.reason);
});