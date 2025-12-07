"""Member API routes."""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from meshcore_hub.api.auth import RequireAdmin, RequireRead
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Member, MemberNode, Node
from meshcore_hub.common.schemas.members import (
    MemberCreate,
    MemberList,
    MemberNodeRead,
    MemberRead,
    MemberUpdate,
)

router = APIRouter()


def _enrich_member_nodes(
    member: Member, node_info: dict[str, dict]
) -> list[MemberNodeRead]:
    """Enrich member nodes with node details from the database.

    Args:
        member: The member with nodes to enrich
        node_info: Dict mapping public_key to node details

    Returns:
        List of MemberNodeRead with node details populated
    """
    enriched_nodes = []
    for mn in member.nodes:
        info = node_info.get(mn.public_key, {})
        enriched_nodes.append(
            MemberNodeRead(
                public_key=mn.public_key,
                node_role=mn.node_role,
                created_at=mn.created_at,
                updated_at=mn.updated_at,
                node_name=info.get("name"),
                node_adv_type=info.get("adv_type"),
                tag_name=info.get("tag_name"),
            )
        )
    return enriched_nodes


def _member_to_read(member: Member, node_info: dict[str, dict]) -> MemberRead:
    """Convert a Member model to MemberRead with enriched node data."""
    return MemberRead(
        id=member.id,
        name=member.name,
        callsign=member.callsign,
        role=member.role,
        description=member.description,
        contact=member.contact,
        nodes=_enrich_member_nodes(member, node_info),
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.get("", response_model=MemberList)
async def list_members(
    _: RequireRead,
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> MemberList:
    """List all members with pagination."""
    # Get total count
    count_query = select(func.count()).select_from(Member)
    total = session.execute(count_query).scalar() or 0

    # Get members with nodes eagerly loaded
    query = (
        select(Member)
        .options(selectinload(Member.nodes))
        .order_by(Member.name)
        .limit(limit)
        .offset(offset)
    )
    members = list(session.execute(query).scalars().all())

    # Collect all public keys from member nodes
    all_public_keys = set()
    for m in members:
        for mn in m.nodes:
            all_public_keys.add(mn.public_key)

    # Fetch node info for all public keys in one query
    node_info: dict[str, dict] = {}
    if all_public_keys:
        node_query = (
            select(Node)
            .options(selectinload(Node.tags))
            .where(Node.public_key.in_(all_public_keys))
        )
        nodes = session.execute(node_query).scalars().all()
        for node in nodes:
            tag_name = None
            for tag in node.tags:
                if tag.key == "name":
                    tag_name = tag.value
                    break
            node_info[node.public_key] = {
                "name": node.name,
                "adv_type": node.adv_type,
                "tag_name": tag_name,
            }

    return MemberList(
        items=[_member_to_read(m, node_info) for m in members],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{member_id}", response_model=MemberRead)
async def get_member(
    _: RequireRead,
    session: DbSession,
    member_id: str,
) -> MemberRead:
    """Get a specific member by ID."""
    query = (
        select(Member).options(selectinload(Member.nodes)).where(Member.id == member_id)
    )
    member = session.execute(query).scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Fetch node info for member's nodes
    node_info: dict[str, dict] = {}
    public_keys = [mn.public_key for mn in member.nodes]
    if public_keys:
        node_query = (
            select(Node)
            .options(selectinload(Node.tags))
            .where(Node.public_key.in_(public_keys))
        )
        nodes = session.execute(node_query).scalars().all()
        for node in nodes:
            tag_name = None
            for tag in node.tags:
                if tag.key == "name":
                    tag_name = tag.value
                    break
            node_info[node.public_key] = {
                "name": node.name,
                "adv_type": node.adv_type,
                "tag_name": tag_name,
            }

    return _member_to_read(member, node_info)


@router.post("", response_model=MemberRead, status_code=201)
async def create_member(
    _: RequireAdmin,
    session: DbSession,
    member: MemberCreate,
) -> MemberRead:
    """Create a new member."""
    # Create member
    new_member = Member(
        name=member.name,
        callsign=member.callsign,
        role=member.role,
        description=member.description,
        contact=member.contact,
    )
    session.add(new_member)
    session.flush()  # Get the ID for the member

    # Add nodes if provided
    if member.nodes:
        for node_data in member.nodes:
            node = MemberNode(
                member_id=new_member.id,
                public_key=node_data.public_key.lower(),
                node_role=node_data.node_role,
            )
            session.add(node)

    session.commit()
    session.refresh(new_member)

    return MemberRead.model_validate(new_member)


@router.put("/{member_id}", response_model=MemberRead)
async def update_member(
    _: RequireAdmin,
    session: DbSession,
    member_id: str,
    member: MemberUpdate,
) -> MemberRead:
    """Update a member."""
    query = (
        select(Member).options(selectinload(Member.nodes)).where(Member.id == member_id)
    )
    existing = session.execute(query).scalar_one_or_none()

    if not existing:
        raise HTTPException(status_code=404, detail="Member not found")

    # Update fields
    if member.name is not None:
        existing.name = member.name
    if member.callsign is not None:
        existing.callsign = member.callsign
    if member.role is not None:
        existing.role = member.role
    if member.description is not None:
        existing.description = member.description
    if member.contact is not None:
        existing.contact = member.contact

    # Update nodes if provided (replaces existing nodes)
    if member.nodes is not None:
        # Clear existing nodes
        existing.nodes.clear()

        # Add new nodes
        for node_data in member.nodes:
            node = MemberNode(
                member_id=existing.id,
                public_key=node_data.public_key.lower(),
                node_role=node_data.node_role,
            )
            existing.nodes.append(node)

    session.commit()
    session.refresh(existing)

    return MemberRead.model_validate(existing)


@router.delete("/{member_id}", status_code=204)
async def delete_member(
    _: RequireAdmin,
    session: DbSession,
    member_id: str,
) -> None:
    """Delete a member."""
    query = select(Member).where(Member.id == member_id)
    member = session.execute(query).scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    session.delete(member)
    session.commit()
