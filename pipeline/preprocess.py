import bpy
import bmesh
import logging

# Configurazione base del logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MeshPreprocessor:
    """
    Classe per il preprocessing delle mesh in Blender:
    - Unione di mesh multiple per materiale
    - Correzione geometria non-manifold
    - Rimozione geometria non connessa (loose)
    - Triangolazione
    """

    @staticmethod
    def _set_active_object(obj):
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

    @staticmethod
    def _get_material_key(obj):
        """
        Genera una chiave univoca per il materiale di un oggetto.
        Se l'oggetto ha più materiali, usa il primo.
        Se non ha materiali, restituisce 'NO_MATERIAL'.
        """
        if obj.data.materials:
            mat = obj.data.materials[0]
            return mat.name if mat else 'NO_MATERIAL'
        return 'NO_MATERIAL'

    @staticmethod
    def group_by_material(root_name: str) -> dict:
        """
        Raggruppa tutti gli oggetti mesh sotto root_name per materiale.
        
        Returns:
            dict: Dizionario {material_name: [list of objects]}
        """
        root = bpy.data.objects.get(root_name)
        if root is None:
            logger.error(f"Root object '{root_name}' not found")
            return {}

        meshes = [obj for obj in root.children_recursive if obj.type == 'MESH']
        
        # Aggiungi la root se è una mesh
        if root.type == 'MESH':
            meshes.append(root)

        if not meshes:
            logger.error("No mesh objects found under the root")
            return {}

        # Raggruppa per materiale
        material_groups = {}
        for mesh in meshes:
            mat_key = MeshPreprocessor._get_material_key(mesh)
            if mat_key not in material_groups:
                material_groups[mat_key] = []
            material_groups[mat_key].append(mesh)

        logger.info(f"Trovati {len(material_groups)} gruppi di materiali:")
        for mat_name, objs in material_groups.items():
            logger.info(f"  - {mat_name}: {len(objs)} oggetti")

        return material_groups

    @staticmethod
    def flatten_and_join_by_material(root_name: str, merge_vertices_threshold: float = None) -> list[bpy.types.Object]:
        """
        Unisce tutte le mesh sotto root_name raggruppandole per materiale.
        
        Returns:
            list: Lista di oggetti mesh uniti, uno per ogni materiale
        """
        material_groups = MeshPreprocessor.group_by_material(root_name)
        
        if not material_groups:
            return []

        joined_meshes = []

        for mat_name, meshes in material_groups.items():
            logger.info(f"Processing material group: {mat_name} ({len(meshes)} objects)")
            
            # Safe flatten: unparent keeping world transform
            for mesh in meshes:
                world_mat = mesh.matrix_world.copy()
                mesh.parent = None
                mesh.matrix_world = world_mat

            # Deselect all
            bpy.ops.object.select_all(action='DESELECT')

            # Select all meshes in this group
            for mesh in meshes:
                mesh.select_set(True)

            # Make one active
            bpy.context.view_layer.objects.active = meshes[0]

            # Join meshes
            bpy.ops.object.join()
            combined_mesh = bpy.context.view_layer.objects.active
            
            # Rinomina l'oggetto unito
            combined_mesh.name = f"Joined_{mat_name}"

            # Merge vertices if threshold is provided
            if merge_vertices_threshold is not None:
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.remove_doubles(threshold=merge_vertices_threshold)
                bpy.ops.object.mode_set(mode='OBJECT')

            joined_meshes.append(combined_mesh)
            logger.info(f"  -> Created: {combined_mesh.name}")

        return joined_meshes

    @staticmethod
    def flatten_and_join(root_name: str, merge_vertices_threshold: float = None) -> bpy.types.Object:
        """
        Flatten the hierarchy under `root_name` by removing all parents,
        applying parent transforms, and joining all meshes into a single one.
        Optionally merge vertices by distance.
        
        NOTA: Questo metodo unisce TUTTO in una singola mesh.
        Per mantenere i materiali separati, usa flatten_and_join_by_material()
        """
        root = bpy.data.objects.get(root_name)
        if root is None:
            logger.error(f"Root object '{root_name}' not found")
            return None

        meshes = [obj for obj in root.children_recursive if obj.type == 'MESH']
        
        # Aggiungiamo anche la root se è una mesh
        if root.type == 'MESH':
            meshes.append(root)

        if not meshes:
            logger.error("No mesh objects found under the root")
            return None

        # Safe flatten: unparent keeping world transform
        for mesh in meshes:
            world_mat = mesh.matrix_world.copy()
            mesh.parent = None
            mesh.matrix_world = world_mat

        # Deselect all
        bpy.ops.object.select_all(action='DESELECT')

        # Select all meshes
        for mesh in meshes:
            mesh.select_set(True)

        # Make one active
        bpy.context.view_layer.objects.active = meshes[0]

        # Join meshes
        bpy.ops.object.join()
        combined_mesh = bpy.context.view_layer.objects.active
        
        if merge_vertices_threshold is not None:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.remove_doubles(threshold=merge_vertices_threshold)
            bpy.ops.object.mode_set(mode='OBJECT')

        return combined_mesh

    @staticmethod
    def clean_and_fix(obj: bpy.types.Object):
        """
        Esegue la pulizia della mesh:
        1. Select & Fix non-manifold (rimozione doppi, riempimento buchi semplici)
        2. Remove loose geometry
        3. Triangolazione
        """
        if obj is None or obj.type != 'MESH':
            logger.warning("Oggetto non valido per il preprocessing.")
            return

        logger.info(f"Avvio pulizia mesh per: {obj.name}")
        
        MeshPreprocessor._set_active_object(obj)
        
        # Passa in Edit Mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 1. Merge by distance (Remove Doubles) - Spesso risolve non-manifold basilari
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=0.0001)
        
        # 2. Fix Non-Manifold (Tentativo di riempimento buchi)
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_non_manifold()
        bpy.ops.mesh.fill_holes(sides=0) # 0 = infinite sides allowed
        
        # 3. Remove Loose Geometry (vertici/bordi/facce isolati)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete_loose()
        
        # 4. Ricalcola le normali e rimuovi sharp edges
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.mark_sharp(clear=True)
        # Cancella custom split normals se presenti
        if obj.data.has_custom_normals:
             bpy.ops.mesh.customdata_custom_splitnormals_clear()
             
        bpy.ops.mesh.normals_make_consistent(inside=False)

        # 5. Triangulate
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
        
        # Torna in Object Mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        logger.info(f"Preprocessing completato per: {obj.name}")

    @staticmethod
    def process_by_material(root_name: str, merge_vertices_threshold: float = None) -> list[bpy.types.Object]:
        """
        Pipeline principale per processare mantenendo i materiali separati:
        1. Raggruppa per materiale
        2. Join per ogni gruppo
        3. Clean & Triangulate ogni mesh
        
        Returns:
            list: Lista di oggetti mesh processati, uno per ogni materiale
        """
        # 1. Join per materiale
        joined_meshes = MeshPreprocessor.flatten_and_join_by_material(
            root_name, 
            merge_vertices_threshold
        )
        
        if not joined_meshes:
            logger.warning("Nessuna mesh da processare")
            return []
        
        # 2. Clean, Fix & Triangulate ogni mesh
        for mesh in joined_meshes:
            MeshPreprocessor.clean_and_fix(mesh)
        
        logger.info(f"Processo completato: {len(joined_meshes)} mesh finali")
        return joined_meshes

    @staticmethod
    def process(root_name: str, merge_vertices_threshold: float = None) -> bpy.types.Object:
        """
        Pipeline principale originale: Join tutto -> Clean -> Triangulate
        
        DEPRECATO: Usa process_by_material() per mantenere i materiali separati
        
        Restituisce l'oggetto finale processato.
        """
        logger.warning("Attenzione: process() unisce tutto in una singola mesh. Usa process_by_material() per mantenere i materiali separati.")
        
        # 1. Join (Flatten) tutto
        final_mesh = MeshPreprocessor.flatten_and_join(root_name, merge_vertices_threshold)
        
        if final_mesh is None:
            return None
        
        # 2. Clean, Fix & Triangulate
        MeshPreprocessor.clean_and_fix(final_mesh)
        
        return final_mesh